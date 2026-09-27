"""Runs read from MLflow: analyses and training."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from mlflow import MlflowClient
from mlflow.entities import Run

from loupe.core import tracking_uri
from loupe.stores.types import Artifact, MetricPoint, RunDetail, RunSummary

PREFIX = "m-"


def _client() -> MlflowClient | None:
    uri = tracking_uri()
    if uri.startswith("sqlite:///") and not os.path.exists(uri.removeprefix("sqlite:///")):
        return None  # nothing tracked yet; do not create an empty database by reading
    return MlflowClient(tracking_uri=uri)


def _summary(run: Run, experiment: str | None) -> RunSummary:
    tags = run.data.tags
    kind = tags.get("loupe.kind", "analysis")
    return RunSummary(
        id=PREFIX + run.info.run_id,
        kind=kind if kind in ("analysis", "training") else "analysis",  # type: ignore[arg-type]
        name=run.info.run_name or run.info.run_id[:8],
        experiment=experiment if experiment != "Default" else None,
        status=run.info.status.lower(),
        created=datetime.fromtimestamp(run.info.start_time / 1000, UTC),
        model=run.data.params.get("model"),
        metrics=dict(run.data.metrics),
        samples=None,
    )


def list_runs() -> list[RunSummary]:
    client = _client()
    if client is None:
        return []
    names = {e.experiment_id: e.name for e in client.search_experiments()}
    if not names:
        return []
    runs = client.search_runs(list(names), max_results=1000)
    return [_summary(r, names.get(r.info.experiment_id)) for r in runs]


def get_run(run_id: str) -> RunDetail | None:
    client = _client()
    if client is None:
        return None
    try:
        run = client.get_run(run_id.removeprefix(PREFIX))
    except Exception:
        return None
    experiment = client.get_experiment(run.info.experiment_id).name
    history = {
        key: [
            MetricPoint(step=m.step, value=m.value)
            for m in client.get_metric_history(run.info.run_id, key)
        ]
        for key in run.data.metrics
    }
    artifacts = [
        Artifact(path=a.path, size=a.file_size)
        for a in client.list_artifacts(run.info.run_id)
        if not a.is_dir
    ]
    return RunDetail(
        **_summary(run, experiment).model_dump(),
        params=dict(run.data.params),
        tags={k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")},
        history=history,
        artifacts=artifacts,
        scorers=[],
        error=None,
    )


def read_artifact(run_id: str, path: str) -> bytes | None:
    """One artifact's bytes, for JSON tables the UI renders."""
    client = _client()
    if client is None:
        return None
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            local = client.download_artifacts(run_id.removeprefix(PREFIX), path, tmp)
            with open(local, "rb") as f:
                return f.read()
    except Exception:
        return None
