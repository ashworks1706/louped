"""Runs read from MLflow: analyses and training."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from mlflow import MlflowClient
from mlflow.entities import Run

from louped.core import tracking_uri
from louped.stores.types import Artifact, MetricPoint, RunDetail, RunSummary

PREFIX = "m-"

# The server reads artifacts per request; MLflow's download progress bars would fill its log.
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")


def _client() -> MlflowClient | None:
    uri = tracking_uri()
    if uri.startswith("sqlite:///") and not os.path.exists(uri.removeprefix("sqlite:///")):
        return None  # nothing tracked yet; do not create an empty database by reading
    return MlflowClient(tracking_uri=uri)


def _missing(exc: Exception) -> bool:
    """Whether MLflow raised because the run or artifact does not exist; anything else (a locked
    database, a schema it cannot read) is a real error and is raised."""
    from mlflow.exceptions import MlflowException

    code = getattr(exc, "error_code", "")
    return isinstance(exc, MlflowException) and code in ("RESOURCE_DOES_NOT_EXIST",
                                                         "INVALID_PARAMETER_VALUE")  # fmt: skip


def _summary(run: Run, experiment: str | None) -> RunSummary:
    tags = run.data.tags
    kind = tags.get("louped.kind", "analysis")
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
        host=tags.get("louped.host"),
    )


def list_runs() -> list[RunSummary]:
    client = _client()
    if client is None:
        return []
    names = {e.experiment_id: e.name for e in client.search_experiments()}
    if not names:
        return []
    runs, token = [], None
    while True:
        page = client.search_runs(list(names), max_results=1000, page_token=token)
        runs.extend(page)
        token = page.token
        if not token:
            break
    return [_summary(r, names.get(r.info.experiment_id)) for r in runs]


def get_run(run_id: str) -> RunDetail | None:
    client = _client()
    if client is None:
        return None
    try:
        run = client.get_run(run_id.removeprefix(PREFIX))
    except Exception as exc:
        if _missing(exc):
            return None
        raise
    experiment = client.get_experiment(run.info.experiment_id).name
    history = {
        key: [
            MetricPoint(step=m.step, value=m.value, timestamp=m.timestamp)
            for m in client.get_metric_history(run.info.run_id, key)
        ]
        for key in run.data.metrics
    }
    artifacts = _walk(client, run.info.run_id, None)
    return RunDetail(
        **_summary(run, experiment).model_dump(),
        params=dict(run.data.params),
        tags={k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")},
        history=history,
        artifacts=artifacts,
        scorers=[],
        error=None,
    )


def _walk(client: MlflowClient, run_id: str, path: str | None) -> list[Artifact]:
    out: list[Artifact] = []
    for a in client.list_artifacts(run_id, path):
        out.extend(
            _walk(client, run_id, a.path) if a.is_dir else [Artifact(path=a.path, size=a.file_size)]
        )
    return out


def list_artifact_paths(run_id: str, path: str) -> list[str] | None:
    """Every file under path, recursively; None when the run does not exist."""
    client = _client()
    if client is None:
        return None
    run_id = run_id.removeprefix(PREFIX)
    try:
        client.get_run(run_id)
    except Exception as exc:
        if _missing(exc):
            return None
        raise
    return [a.path for a in _walk(client, run_id, path)]


def write_markdown(run_id: str, path: str, text: str) -> bool:
    """Replace a Markdown file a run already logged, in its local artifact folder; False when the
    run or file is not there. Refused for anything but .md, and for a store that is not local."""
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("bad path")
    if not path.endswith(".md"):
        raise ValueError("only a run's Markdown files are edited here")
    artifact_path = Path(path)
    if artifact_path.is_absolute() or ".." in artifact_path.parts:
        raise ValueError("bad path")
    client = _client()
    if client is None:
        return False
    try:
        uri = client.get_run(run_id.removeprefix(PREFIX)).info.artifact_uri or ""
    except Exception as exc:
        if _missing(exc):
            return False
        raise
    if not uri.startswith("file://") and not uri.startswith("/"):
        raise ValueError(f"{run_id}'s artifacts are not on this machine ({uri})")
    folder = Path(uri.removeprefix("file://")).resolve()
    target = (folder / rel).resolve()
    if not target.is_relative_to(folder) or not target.is_file():
        return False
    target.write_text(text, encoding="utf-8")
    return True


def read_artifact(run_id: str, path: str) -> bytes | None:
    """One artifact's bytes, for JSON tables the UI renders."""
    client = _client()
    if client is None:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            local = client.download_artifacts(run_id.removeprefix(PREFIX), path, tmp)
            with open(local, "rb") as f:
                return f.read()
    except OSError:  # no such artifact: MLflow's local store raises it as a missing file
        return None
    except Exception as exc:
        if _missing(exc):
            return None
        raise
