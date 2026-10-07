"""A script over a run's files, kept with the run: new per-item columns, or a figure.

The script is a Python file in the project (experiments/<name>/derive/<what>.py, to commit)
with a function `derive(files: Path)`: files is a folder holding a copy of every file the run
logged. It returns rows or a figure:

- rows, a list of dicts each with the records' key (qid): logged as derived/<name>.jsonl, which
  the run's Items tab shows as columns <name>.<field> beside the conditions;
- a figure, a dict with a "kind" as louped.analysis.views makes them (plotly for points in 3D):
  logged as views/<name>.json, on the run's Figures tab.

The script is logged beside what it made (derived/<name>.py), with the commit and packages it
ran under and the file it made (derived/<name>.meta.json, its "output"), and the run's
louped.added tag lists all three, so the run says what was added to it and how. It runs as a job
from the queue, so one that embeds text on the GPU waits its turn.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from louped.core import capture
from louped.core.paths import NAME
from louped.stores import mlflow_runs
from louped.stores.items import KEY_NAMES
from louped.stores.types import View


def derive(run_id: str, script: Path, name: str | None = None) -> str:
    """Run script's derive() over a copy of the run's files and log what it returns into the
    run; returns the path it was logged as."""
    name = name or script.stem.replace("_", "-").lower()
    if not NAME.match(name):
        raise ValueError(f"{name!r} is not a name: lowercase letters, digits and -")
    if not run_id.startswith(mlflow_runs.PREFIX):
        raise ValueError(f"{run_id} is not an MLflow run (an analysis or training run)")
    fn = _load(script)
    with tempfile.TemporaryDirectory() as tmp:
        files = Path(tmp)
        if not mlflow_runs.download_all(run_id, files):
            raise FileNotFoundError(f"no run {run_id}")
        out = fn(files)
    path, text = _logged(name, out)
    for where, what in (
        (path, text),
        (f"derived/{name}.py", script.read_text(encoding="utf-8")),
        (
            f"derived/{name}.meta.json",
            json.dumps(
                {**capture(script=script).model_dump(mode="json"), "output": path}, indent=2
            ),
        ),
    ):
        if not mlflow_runs.add_text(run_id, where, what):
            raise FileNotFoundError(f"no run {run_id}")
    return path


def _load(script: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"louped_derive_{script.stem}", script)
    if spec is None or spec.loader is None:
        raise ValueError(f"{script} is not a Python file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "derive", None)
    if not callable(fn):
        raise ValueError(f"{script} has no derive(files) function")
    return fn


def _logged(name: str, out: Any) -> tuple[str, str]:
    """Where what derive() returned goes, and its text."""
    if isinstance(out, dict) and "kind" in out:
        try:
            view = TypeAdapter(View).validate_python(out)
        except ValidationError as exc:
            raise ValueError(f"derive() returned a figure that is not one: {exc}") from exc
        dumped = TypeAdapter(View).dump_python(view, mode="json", exclude_none=True)
        return f"views/{name}.json", json.dumps(dumped, indent=2)
    if isinstance(out, list) and out and all(isinstance(r, dict) for r in out):
        if keyless := [i for i, r in enumerate(out) if not set(r) & set(KEY_NAMES)]:
            raise ValueError(f"derive() returned rows without the records' key, one of "
                             f"{', '.join(KEY_NAMES)}: row {keyless[0]} has "
                             f"{sorted(out[keyless[0]])}")  # fmt: skip
        return f"derived/{name}.jsonl", "".join(json.dumps(r) + "\n" for r in out)
    raise ValueError("derive() returns rows (a list of dicts) or a figure (a dict with a kind)")
