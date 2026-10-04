"""circuit-tracer's attribution graphs under <home>/graphs, from the metadata file it writes."""

from __future__ import annotations

import json

from louped.core import graphs_dir
from louped.stores.types import Graph


def list_graphs() -> list[Graph]:
    """The graphs in circuit-tracer's metadata file, newest last; none when there is no file."""
    meta = graphs_dir() / "graph-metadata.json"
    if not meta.exists():
        return []
    return [Graph.model_validate(g) for g in json.loads(meta.read_text())["graphs"]]
