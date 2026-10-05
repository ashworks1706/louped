"""Notebooks run as jobs: an experiment's .ipynb, executed by papermill inside a run.

A notebook's parameters are the variables of its cell tagged "parameters" (in Jupyter, the cell's
tags; a notebook from Colab needs the tag added). A run's values replace them: papermill adds a
cell after that one, holding them.

The notebook runs in an IPython kernel of louped's own environment, in its own folder, so it reads
files beside it as Jupyter would. Its run is in the notebook's experiment; the kernel finds it in
MLFLOW_RUN_ID and MLFLOW_TRACKING_URI, so mlflow.log_* and louped.tracking.log_json in a cell log
to it. The run keeps its parameters and the executed copy, notebook/<name>.ipynb, with every
cell's output. A cell that raises fails the run, and the copy still shows the cells up to it.
"""

from __future__ import annotations

import ast
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from louped.core.paths import experiments_dir
from louped.stores import mlflow_runs
from louped.tracking import start_run

#: Where a run keeps its executed notebook.
FOLDER = "notebook"
#: The parameter types a value is checked against.
TYPES = ("int", "float", "str", "bool")


class Parameter(BaseModel):
    name: str
    #: Its value in the notebook, as Python source.
    default: str
    #: int, float, str or bool: its annotation's, else its default's; None for any other.
    type: str | None = None
    #: Its comment in the notebook.
    help: str = ""


def parameters(path: Path) -> list[Parameter]:
    """The notebook's parameters, from its cell tagged "parameters"; none when it has no such
    cell."""
    from papermill.inspection import inspect_notebook

    found = inspect_notebook(str(path)).values()
    return [Parameter(name=p["name"], default=p["default"], help=p["help"],
                      type=_type(p["inferred_type_name"], p["default"]))
            for p in found]  # fmt: skip


def values(path: Path, given: dict[str, str]) -> dict[str, object]:
    """Text values as the notebook's parameters take them. A parameter typed int, float or bool
    must parse as one; any other value is read as a Python literal (a list, None, a quoted
    string), and is text when it is not one. ValueError for a name the notebook does not have."""
    known = {p.name: p for p in parameters(path)}
    out: dict[str, object] = {}
    for name, text in given.items():
        if name not in known:
            raise ValueError(f"{path.name} has no parameter {name!r}: it has {', '.join(known)}")
        out[name] = _parse(name, text, known[name].type)
    return out


def run_notebook(path: Path, given: dict[str, str] | None = None) -> str:
    """Execute a notebook in experiments/<name>/ with the given parameters, inside a new run in
    that experiment; returns the run's id (m-…). Raises papermill's error for a failing cell,
    after the run has kept the executed copy."""
    import mlflow
    import papermill

    path = path.resolve()
    root = experiments_dir().resolve()
    if not path.is_relative_to(root) or path.suffix != ".ipynb":
        raise ValueError(f"{path} is not a notebook in {root}")
    experiment = path.relative_to(root).parts[0]
    params = values(path, given or {})
    with (start_run(experiment, name=path.stem, params=params or None, kind="notebook") as run,
          tempfile.TemporaryDirectory() as tmp):  # fmt: skip
        executed = Path(tmp) / path.name
        env = {"MLFLOW_RUN_ID": run.info.run_id, "MLFLOW_TRACKING_URI": mlflow.get_tracking_uri()}
        before = {k: os.environ.get(k) for k in env}
        os.environ.update(env)  # the kernel starts with this process's environment
        try:
            papermill.execute_notebook(str(path), str(executed), parameters=params,
                                       kernel_name="python3", cwd=str(path.parent),
                                       progress_bar=False)  # fmt: skip
        finally:
            for k, v in before.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            if executed.is_file():
                mlflow.log_artifact(str(executed), FOLDER)
        return mlflow_runs.PREFIX + run.info.run_id


def _type(annotated: str | None, default: str) -> str | None:
    if annotated in TYPES:
        return annotated
    try:
        name = type(ast.literal_eval(default)).__name__
    except (ValueError, SyntaxError):  # a default that is an expression, such as Path("x")
        return None
    return name if name in TYPES else None


def _parse(name: str, text: str, kind: str | None) -> object:
    match kind:
        case "str":
            return text
        case "bool":
            if text.lower() not in ("true", "false"):
                raise ValueError(f"{name} is a bool: true or false, not {text!r}")
            return text.lower() == "true"
        case "int" | "float":
            try:
                return int(text) if kind == "int" else float(text)
            except ValueError:
                what = "an int" if kind == "int" else "a float"
                raise ValueError(f"{name} is {what}, not {text!r}") from None
        case _:
            try:
                return ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return text
