"""Notebooks run as jobs: an experiment's .ipynb, executed by papermill inside a run.

A notebook's parameters are the variables of its cell tagged "parameters" (in Jupyter, the cell's
tags; a notebook from Colab needs the tag added). A run's values replace them: papermill adds a
cell after that one, holding them.

The notebook runs in an IPython kernel started from louped's own Python (not a kernel installed
elsewhere under the same name), in the notebook's folder, so it reads files beside it as Jupyter
would. Its run is in the notebook's experiment; the kernel's environment names it
(MLFLOW_RUN_ID, MLFLOW_TRACKING_URI), so mlflow.log_* and louped.tracking.log_json in a cell log
to it. The run keeps every parameter's value and the executed copy, notebook/<name>.ipynb, with
every cell's output. A cell that raises fails the run, and the copy still shows the cells up to
it.
"""

from __future__ import annotations

import ast
import json
import sys
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
    #: Its value as a run's value is written: a str without its quotes, else the source.
    shown: str
    #: int, float, str or bool: its annotation's, else its default's; None for any other.
    type: str | None = None
    #: Its comment in the notebook.
    help: str = ""


def parameters(path: Path) -> list[Parameter]:
    """The notebook's parameters, from its cell tagged "parameters"; none when it has no such
    cell."""
    from papermill.inspection import inspect_notebook

    found = inspect_notebook(str(path)).values()
    out = []
    for p in found:
        kind = _type(p["inferred_type_name"], p["default"])
        shown = str(ast.literal_eval(p["default"])) if kind == "str" else p["default"]
        out.append(Parameter(name=p["name"], default=p["default"], shown=shown, type=kind,
                             help=p["help"]))  # fmt: skip
    return out


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
    from jupyter_client.kernelspec import KernelSpecManager
    from jupyter_client.manager import KernelManager

    path = path.resolve()
    root = experiments_dir().resolve()
    if not path.is_relative_to(root) or path.suffix != ".ipynb":
        raise ValueError(f"{path} is not a notebook in {root}")
    experiment = path.relative_to(root).parts[0]
    params = values(path, given or {})
    logged = {p.name: p.shown for p in parameters(path)} | (given or {})
    with (start_run(experiment, name=path.stem, params=logged or None, kind="notebook") as run,
          tempfile.TemporaryDirectory() as tmp):  # fmt: skip
        executed = Path(tmp) / path.name
        env = {"MLFLOW_RUN_ID": run.info.run_id, "MLFLOW_TRACKING_URI": mlflow.get_tracking_uri()}
        # python3, as notebooks name their kernel, but only this one: louped's Python, this run
        spec = Path(tmp) / "kernels" / "python3"
        spec.mkdir(parents=True)
        (spec / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Python 3", "language": "python", "env": env}))  # fmt: skip
        specs = KernelSpecManager(kernel_dirs=[str(spec.parent)], ensure_native_kernel=False)
        kernel = KernelManager(kernel_name="python3", kernel_spec_manager=specs)
        try:
            papermill.execute_notebook(str(path), str(executed), parameters=params,
                                       kernel_name="python3", km=kernel, cwd=str(path.parent),
                                       progress_bar=False)  # fmt: skip
        finally:
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
