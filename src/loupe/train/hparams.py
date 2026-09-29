"""A training config over a grid of values: every combination a training run of its own, and one
summary run whose figures compare them.

    loupe train sft sft.yaml --sweep train.learning_rate=1e-4,2e-4 --sweep lora.r=8,16

A --sweep is a dotted key of the config and its values, comma separated, each read as YAML (so
1e-4 is a number and true a bool). Every combination trains as `<name>-<n>` in
`<output_dir>/<n>`, with any export name suffixed the same way so none overwrites another, and is
tagged loupe.sweep. The summary run holds each logged series by step, one line per combination,
and a table of their final values linking every run.
"""

from __future__ import annotations

import copy
import itertools
import tempfile
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from loupe.analysis import line, table
from loupe.train.base import TrainError

#: The series a summary compares, when a run logged them.
SERIES = ("loss", "eval_loss", "reward", "rewards/accuracies")


def combinations(sweep: list[str]) -> list[dict[str, Any]]:
    """Every combination of the --sweep values, in order: [{"train.learning_rate": 1e-4}, ...]."""
    axes: list[tuple[str, list[Any]]] = []
    for spec in sweep:
        key, sep, values = spec.partition("=")
        if not sep or not key or not values:
            raise TrainError(f"--sweep {spec!r}: expected key=value,value")
        axes.append((key.strip(), [_value(v) for v in values.split(",")]))
    keys = [k for k, _ in axes]
    return [
        dict(zip(keys, combo, strict=True)) for combo in itertools.product(*(v for _, v in axes))
    ]


def _value(text: str) -> Any:
    """A value as YAML reads it, and 1e-4 as a number, which YAML 1.1 leaves a string."""
    value = yaml.safe_load(text.strip())
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _set(data: dict[str, Any], key: str, value: Any) -> None:
    node = data
    *path, last = key.split(".")
    for part in path:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise TrainError(f"--sweep {key}: {part} is not a section of the config")
    node[last] = value


def variant(raw: dict[str, Any], values: dict[str, Any], n: int) -> dict[str, Any]:
    """The config for one combination, its name, output and exports made its own."""
    data = copy.deepcopy(raw)
    for key, value in values.items():
        _set(data, key, value)
    data["name"] = f"{data['name']}-{n}"
    data["output_dir"] = f"{data['output_dir']}/{n}"
    data.setdefault("experiment", raw.get("experiment") or raw["name"])
    export = data.get("export") or {}
    for key in ("merge_as", "adapter_as"):
        if export.get(key):
            export[key] = f"{export[key]}-{n}"
    return data


def run(recipe: ModuleType, config: Path, sweep: list[str], base_dir: Path | None = None) -> str:
    """Train every combination, then log the summary; returns the summary run's id."""
    import mlflow
    from mlflow.tracking import MlflowClient

    from loupe.core import tracking_uri
    from loupe.stores import get_run
    from loupe.tracking import log_json, start_run

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    combos = combinations(sweep)
    sweep_id = uuid.uuid4().hex[:8]
    children: list[tuple[dict[str, Any], str]] = []
    for n, values in enumerate(combos):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / config.name
            path.write_text(yaml.safe_dump(variant(raw, values, n)), encoding="utf-8")
            cfg = recipe.load_config(path)
            if hasattr(cfg, "_base_dir"):
                cfg._base_dir = base_dir or config.parent
            print(f"sweep {n + 1}/{len(combos)}: {values}")
            recipe.train(cfg)
        last = mlflow.last_active_run()
        if last is None:
            raise TrainError("a sweep run did not log to MLflow")
        MlflowClient(tracking_uri()).set_tag(last.info.run_id, "loupe.sweep", sweep_id)
        children.append((values, f"m-{last.info.run_id}"))

    labels = [", ".join(f"{k}={v}" for k, v in values.items()) for values, _ in children]
    histories = [get_run(run_id).history for _, run_id in children]
    experiment = raw.get("experiment") or raw["name"]
    params = {"config": str(config), "sweep": sweep, "runs": len(children), "sweep_id": sweep_id}
    with start_run(experiment, name=f"sweep · {raw['name']}", params=params) as parent:
        k = 0
        names = [s for s in SERIES if any(s in h for h in histories)]
        for name in names:
            steps = sorted({p.step for h in histories for p in h.get(name, [])})
            series = {label: _held(h[name], steps)
                      for label, h in zip(labels, histories, strict=True)
                      if h.get(name)}  # fmt: skip
            view = line(f"{name} by step", [float(s) for s in steps], series, "step", name,
                        note="one line per combination")  # fmt: skip
            log_json(view, f"views/{k:02d}-{name.replace('/', '-')}.json")
            k += 1
        keys = list(combos[0]) if combos else []
        rows, links = [], []
        for (values, run_id), h in zip(children, histories, strict=True):
            finals = [h[s][-1].value if h.get(s) else None for s in names]
            rows.append([*[str(values[key]) for key in keys], *finals, run_id])
            links.append([*[None] * (len(keys) + len(names)), f"/run/?id={run_id}"])
        log_json(table(f"Sweep of {raw['name']}: final values", [*keys, *names, "run"], rows,
                       note="the last logged value of each series", links=links),
                 f"views/{k:02d}-final.json")  # fmt: skip
        return f"m-{parent.info.run_id}"


def _held(points: list[Any], steps: list[int]) -> list[float]:
    """A run's series on the shared steps, each step holding the last value logged by then (the
    first value before any), so combinations that log on different steps still line up. A run that
    logged nothing of the series is left out of its figure, not drawn as zeros."""
    by_step = {p.step: p.value for p in points}
    out: list[float] = []
    last = points[0].value
    for step in steps:
        last = by_step.get(step, last)
        out.append(float(last))
    return out
