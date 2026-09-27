"""One list of runs across stores, addressed by prefixed ids: e- for eval logs, m- for MLflow."""

from __future__ import annotations

from datetime import UTC, datetime

from loupe.stores import evals, mlflow_runs, views
from loupe.stores.types import RunDetail, RunSummary, RunView, SampleDetail, SampleSummary


class NotFound(LookupError):
    """No run, sample or artifact with that id."""


def list_runs() -> list[RunSummary]:
    runs = evals.list_runs() + mlflow_runs.list_runs()
    epoch = datetime.min.replace(tzinfo=UTC)
    return sorted(runs, key=lambda r: r.created or epoch, reverse=True)


def get_run(run_id: str) -> RunDetail:
    if run_id.startswith(evals.PREFIX):
        run = evals.get_run(run_id)
    elif run_id.startswith(mlflow_runs.PREFIX):
        run = mlflow_runs.get_run(run_id)
    else:
        run = None
    if run is None:
        raise NotFound(run_id)
    return run


def list_samples(run_id: str) -> list[SampleSummary]:
    samples = evals.list_samples(run_id) if run_id.startswith(evals.PREFIX) else None
    if samples is None:
        raise NotFound(run_id)
    return samples


def get_sample(run_id: str, sample_id: str, epoch: int = 1) -> SampleDetail:
    sample = evals.get_sample(run_id, sample_id, epoch) if run_id.startswith(evals.PREFIX) else None
    if sample is None:
        raise NotFound(f"{run_id}/{sample_id}")
    return sample


def read_artifact(run_id: str, path: str) -> bytes:
    data = (
        mlflow_runs.read_artifact(run_id, path) if run_id.startswith(mlflow_runs.PREFIX) else None
    )
    if data is None:
        raise NotFound(f"{run_id}/{path}")
    return data


def list_views(run_id: str) -> list[RunView]:
    if run_id.startswith(evals.PREFIX):
        found = [] if evals.get_run(run_id) is not None else None  # eval logs log no views
    elif run_id.startswith(mlflow_runs.PREFIX):
        found = views.list_views(run_id)
    else:
        found = None
    if found is None:
        raise NotFound(run_id)
    return found
