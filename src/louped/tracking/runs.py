"""A run is an MLflow run under louped's store, with RunMeta attached.

Analyses and training jobs call start_run; the UI finds the result without further wiring. The
experiment is named for the folder under experiments/ that the run answers, which is how the
Experiments page groups runs.

While a run is open, MLflow samples the machine every SAMPLE_SECONDS as system/ metrics: GPU
utilisation, memory and power (NVML), CPU and RAM. NVML sees every process on the GPU, so a model
served by another process on this machine is measured too. LOUPED_SYSTEM_METRICS=0 turns it off.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Run

from louped.core import artifacts_dir, capture, cohorts, tracking_uri

#: Seconds between samples of the machine while a run is open.
SAMPLE_SECONDS = 2


def experiment_id(name: str) -> str:
    """The MLflow experiment named for an experiments/ folder, created with its artifacts under
    louped's home when new."""
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
    script: Path | None = None,
) -> Iterator[Run]:
    """An active MLflow run in louped's store, tagged with its kind and the environment it ran
    in; script is the file that runs it, by default the one Python started on."""
    mlflow.set_tracking_uri(tracking_uri())
    meta = capture(seed=seed, script=script)
    tags = {
        "louped.kind": kind,
        "louped.git_sha": meta.git.sha or "",
        "louped.git_dirty": str(meta.git.dirty).lower(),
        **({"louped.script": meta.script} if meta.script else {}),
    }
    system = os.environ.get("LOUPED_SYSTEM_METRICS", "1") != "0"
    if system:
        mlflow.set_system_metrics_sampling_interval(SAMPLE_SECONDS)
        mlflow.set_system_metrics_samples_before_logging(1)
    with mlflow.start_run(experiment_id=experiment_id(experiment), run_name=name, tags=tags,
                          log_system_metrics=system) as run:  # fmt: skip
        if params:
            mlflow.log_params(params)
        mlflow.log_text(meta.model_dump_json(indent=2), "meta.json")
        yield run


def log_json(obj: Any, path: str) -> None:
    """A JSON artifact on the active run, which the UI can render as a table or figure."""
    mlflow.log_text(json.dumps(obj, indent=2), path)


def cohort_ids(experiment: str, name: str) -> list[str]:
    """The item ids of a cohort saved in the experiment (experiments/<experiment>/cohorts/
    <name>.json), as text; the active run, if any, is tagged louped.cohort with its name and
    size, so its page says it ran on part of the items. FileNotFoundError when there is no such
    cohort."""
    saved = cohorts.read(experiment, name)
    if mlflow.active_run() is not None:
        mlflow.set_tags({"louped.cohort": name, "louped.cohort_n": str(len(saved.ids))})
    return saved.ids
