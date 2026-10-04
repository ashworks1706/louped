"""`louped view <path>`: results someone already has, in the UI, without a project.

It points louped's stores at what it finds and says what it chose: a louped home or MLflow store
(mlflow.db) is read in place; a folder of Inspect logs (*.eval) is read in place beside an empty
home; any other folder of files becomes one run in a throwaway home, so its JSONL, Markdown, JSON
and CSV open in the run page (Items, Artifacts). Nothing is written next to the path.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def prepare(path: Path) -> str:
    """Set the environment louped's stores read for path; returns what will be shown."""
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"{path} is not a folder: give the folder that holds the results")
    if (path / "mlflow.db").is_file():
        _point(path, logs=path / "logs")
        return f"viewing the louped home at {path}"
    scratch = Path(tempfile.mkdtemp(prefix="louped-view-"))
    if next(path.rglob("*.eval"), None) is not None:
        _point(scratch, logs=path)
        return f"viewing the Inspect logs under {path}"
    files = [f for f in path.rglob("*") if f.is_file() and not f.name.startswith(".")]
    if not files:
        raise ValueError(f"{path} holds no files to show")
    _point(scratch, logs=scratch / "logs")
    _as_run(path)
    return f"viewing {len(files)} files under {path} as one run (a copy in {scratch})"


def _point(home: Path, logs: Path) -> None:
    os.environ["LOUPED_HOME"] = str(home)
    os.environ["INSPECT_LOG_DIR"] = str(logs)
    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{home / 'mlflow.db'}"
    os.environ["LOUPED_EXPERIMENTS"] = str(home / "experiments")


def _as_run(folder: Path) -> None:
    """The folder's files as the artifacts of one finished analysis run named for it."""
    from mlflow import MlflowClient

    from louped.core import tracking_uri
    from louped.tracking.runs import experiment_id

    client = MlflowClient(tracking_uri=tracking_uri())
    tags = {"louped.kind": "analysis", "louped.viewed_from": str(folder)}
    run = client.create_run(experiment_id(folder.name), run_name=folder.name, tags=tags)
    client.log_artifacts(run.info.run_id, str(folder))
    client.set_terminated(run.info.run_id, "FINISHED")
