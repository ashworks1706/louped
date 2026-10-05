"""Figures a run logged as JSON under views/, which the Figures tab draws, and the figures an
agent adds: to a run after it ran, or to an experiment as experiments/<name>/views/<view>.json,
the project's to commit, which the experiment's page draws.

A file that does not parse as a view is skipped, not an error: views/ is a convention, and one bad
file should not hide the rest.
"""

from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from louped.core.paths import NAME, experiment_folder, inside
from louped.stores import mlflow_runs
from louped.stores.types import RunView, View

DIR = "views"
#: A figure's name: its file under views/, without .json.
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


def _named(name: str) -> str:
    if not NAME.match(name):
        raise ValueError(f"{name!r} is not a figure name: lowercase letters, digits and -")
    return f"{name}.json"


def add_view(run_id: str, name: str, view: View) -> RunView | None:
    """A figure added to a run after it ran, as views/<name>.json (replacing one of that name);
    None when there is no such MLflow run."""
    path = f"{DIR}/{_named(name)}"
    text = json.dumps(_VIEW.dump_python(view, mode="json", exclude_none=True), indent=2)
    if not run_id.startswith(mlflow_runs.PREFIX) or not mlflow_runs.add_text(run_id, path, text):
        return None
    return RunView(path=path, view=view)


def experiment_views(experiment: str) -> list[RunView]:
    """An experiment's own figures, by file name; FileNotFoundError when there is no such
    experiment. A file that is not a view is skipped."""
    folder = experiment_folder(experiment) / DIR
    out: list[RunView] = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            view = _VIEW.validate_json(path.read_bytes())
        except ValidationError:
            continue
        out.append(RunView(path=f"{DIR}/{path.name}", view=view))
    return out


def save_experiment_view(experiment: str, name: str, view: View) -> RunView:
    """Writes experiments/<experiment>/views/<name>.json, replacing one of that name."""
    path = inside(experiment_folder(experiment), DIR, _named(name))
    path.parent.mkdir(exist_ok=True)
    data = _VIEW.dump_python(view, mode="json", exclude_none=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return RunView(path=f"{DIR}/{path.name}", view=view)
