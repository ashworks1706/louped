"""A run is an MLflow run under loupe's store, with RunMeta attached.

Analyses and training jobs call start_run; the UI finds the result without further wiring. The
experiment is named for the folder under experiments/ that the run answers, which is how the
Experiments page groups runs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Run

from loupe.core import artifacts_dir, capture, tracking_uri


def _experiment_id(name: str) -> str:
    client = MlflowClient(tracking_uri=tracking_uri())
    found = client.get_experiment_by_name(name)
    if found is not None:
        return found.experiment_id
    location = (artifacts_dir() / name).as_uri()
    return client.create_experiment(name, artifact_location=location)


@contextmanager
def start_run(
    experiment: str,
    name: str | None = None,
    params: dict[str, Any] | None = None,
    seed: int | None = None,
    kind: str = "analysis",
) -> Iterator[Run]:
    """An active MLflow run in loupe's store, tagged with its kind and the environment it ran in."""
    mlflow.set_tracking_uri(tracking_uri())
    meta = capture(seed=seed)
    tags = {
        "loupe.kind": kind,
        "loupe.git_sha": meta.git.sha or "",
        "loupe.git_dirty": str(meta.git.dirty).lower(),
    }
    with mlflow.start_run(
        experiment_id=_experiment_id(experiment), run_name=name, tags=tags
    ) as run:
        if params:
            mlflow.log_params(params)
        mlflow.log_text(meta.model_dump_json(indent=2), "meta.json")
        yield run


def log_json(obj: Any, path: str) -> None:
    """A JSON artifact on the active run, which the UI can render as a table or figure."""
    mlflow.log_text(json.dumps(obj, indent=2), path)
