"""Figures a run logged as JSON under views/, which the Figures tab draws.

A file that does not parse as a view is skipped, not an error: views/ is a convention, and one bad
file should not hide the rest.
"""

from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from louped.stores import mlflow_runs
from louped.stores.types import RunView, View

DIR = "views"
_VIEW: TypeAdapter[View] = TypeAdapter(View)


def list_views(run_id: str) -> list[RunView] | None:
    """The views of an MLflow run; None when the run does not exist."""
    paths = mlflow_runs.list_artifact_paths(run_id, DIR)
    if paths is None:
        return None
    out: list[RunView] = []
    for path in sorted(p for p in paths if p.endswith(".json")):
        data = mlflow_runs.read_artifact(run_id, path)
        try:
            out.append(RunView(path=path, view=_VIEW.validate_python(json.loads(data or b""))))
        except (ValidationError, ValueError):
            continue
    return out
