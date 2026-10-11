"""circuit-tracer's attribution graphs under <home>/graphs, from the metadata file it writes, and
each graph read for louped's own view: every node's and edge's share of the influence on the
logits, and the nodes a person pinned."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from louped.core import graphs_dir
from louped.core.paths import inside
from louped.stores.runs import NotFound
from louped.stores.types import (
    CircuitGraph,
    CircuitGroup,
    CircuitLink,
    CircuitNode,
    CircuitPins,
    Graph,
)


def list_graphs() -> list[Graph]:
    """The graphs in circuit-tracer's metadata file, newest last; none when there is no file."""
    meta = graphs_dir() / "graph-metadata.json"
    if not meta.exists():
        return []
    return [Graph.model_validate(g) for g in json.loads(meta.read_text())["graphs"]]


def _file(slug: str) -> Path:
    path = inside(graphs_dir(), f"{slug}.json")
    if path.parent != graphs_dir().resolve() or slug.endswith(".meta"):
        raise ValueError(f"{slug!r} is not a graph's slug")
    if not path.is_file():
        raise NotFound(f"no graph {slug}")
    return path


def _kind(node: dict[str, Any]) -> str:
    kind = str(node.get("feature_type", ""))
    if kind in ("embedding", "logit"):
        return kind
    return "error" if "error" in kind else "feature"


def _depth(layer: str) -> float:
    """Where a layer sits: embeddings below every layer."""
    return -1.0 if layer == "E" else float(layer)


def get_graph(slug: str) -> CircuitGraph:
    """One graph, each node scored over the edges the file keeps: a logit starts with its
    probability, and each node passes what it received down its inputs in proportion to their
    absolute weight. circuit-tracer's own influence, from the graph before it was pruned, comes
    along where the file has it. ValueError when no logit has a probability."""
    data = json.loads(_file(slug).read_text())
    raw = data["nodes"]
    ids = {n["node_id"] for n in raw}
    links = [x for x in data["links"] if x["source"] in ids and x["target"] in ids]
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for x in links:
        incoming[x["target"]].append(x)
    logits = [n for n in raw if _kind(n) == "logit"]
    probs = {n["node_id"]: float(n.get("token_prob") or 0) for n in logits}
    total = sum(probs.values())
    if total <= 0:
        raise ValueError(f"graph {slug} has no logit with a probability (token_prob)")
    received = {i: probs.get(i, 0.0) / total for i in ids}
    share: dict[tuple[str, str], float] = {}
    # top layer down: a node has received all it will by the time its layer is reached
    for n in sorted(raw, key=lambda n: -_depth(str(n["layer"]))):
        came = received[n["node_id"]]
        ins = incoming[n["node_id"]]
        mass = sum(abs(x["weight"]) for x in ins)
        if not came or not mass:
            continue
        for x in ins:
            s = came * abs(x["weight"]) / mass
            share[(x["source"], x["target"])] = s
            received[x["source"]] += s
    rows = {la: i for i, la in enumerate(sorted({str(n["layer"]) for n in raw}, key=_depth))}
    tokens = data["metadata"].get("prompt_tokens") or []
    nodes = [
        CircuitNode(
            id=n["node_id"],
            kind=_kind(n),  # type: ignore[arg-type]
            layer=str(n["layer"]),
            row=rows[str(n["layer"])],
            position=int(n["ctx_idx"]),
            feature=n.get("feature"),
            label=n.get("clerp") or _label(n, tokens),
            activation=n.get("activation"),
            prob=n.get("token_prob") if _kind(n) == "logit" else None,
            target=bool(n.get("is_target_logit")),
            score=round(received[n["node_id"]], 6),
            influence=n.get("influence") if _kind(n) != "logit" else None,
        )
        for n in raw
    ]
    q = data.get("qParams") or {}
    return CircuitGraph(
        slug=slug,
        prompt=data["metadata"].get("prompt", ""),
        tokens=tokens,
        scan=data["metadata"].get("scan"),
        nodes=nodes,
        links=[
            CircuitLink(
                source=x["source"],
                target=x["target"],
                weight=x["weight"],
                share=round(share.get((x["source"], x["target"]), 0.0), 6),
            )
            for x in links
        ],
        **_pins(q, ids).model_dump(),
    )


def _label(n: dict[str, Any], tokens: list[str]) -> str:
    kind, pos = _kind(n), int(n["ctx_idx"])
    word = tokens[pos] if pos < len(tokens) else ""
    if kind == "embedding":
        return word
    if kind == "error":
        return f"error at layer {n['layer']}, {word!r}"
    return f"feature {n['layer']}.{n.get('feature')}"


def _pins(q: dict[str, Any], ids: set[str]) -> CircuitPins:
    """qParams as louped reads it: pinnedIds (a list, or circuit-tracer's comma-joined text) and
    supernodes [name, id, ...]; ids the graph no longer has are dropped."""
    pinned = q.get("pinnedIds") or []
    if isinstance(pinned, str):
        pinned = pinned.split(",")
    groups = []
    for g in q.get("supernodes") or []:
        if isinstance(g, list) and len(g) > 1 and (kept := [i for i in g[1:] if i in ids]):
            groups.append(CircuitGroup(name=str(g[0]) or "group", nodes=kept))
    return CircuitPins(pinned=[i for i in pinned if i in ids], groups=groups)


def save_pins(slug: str, pins: CircuitPins) -> CircuitPins:
    """Writes the pins into the graph file's qParams, where circuit-tracer's viewer reads them;
    ValueError naming a node the graph does not have."""
    path = _file(slug)
    data = json.loads(path.read_text())
    ids = {n["node_id"] for n in data["nodes"]}
    named = [*pins.pinned, *(i for g in pins.groups for i in g.nodes)]
    if missing := [i for i in dict.fromkeys(named) if i not in ids]:
        raise ValueError(f"graph {slug} has no node {', '.join(missing[:5])}")
    q = data.get("qParams") or {}
    q["pinnedIds"] = list(dict.fromkeys(pins.pinned))
    q["supernodes"] = [[g.name, *g.nodes] for g in pins.groups]
    data["qParams"] = q
    # a reader mid-write would see half a file: write beside it, then swap
    part = path.with_suffix(".json.part")
    part.write_text(json.dumps(data))
    os.replace(part, path)
    return pins
