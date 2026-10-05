"""Runs read from MLflow: analyses and training."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
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


#: The text files a run logged that can be edited in place.
EDITABLE = (".md", ".txt", ".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".yaml", ".yml", ".toml")
#: The tag naming the files edited after the run, so the run says it was changed.
EDITED = "louped.edited"


def write_text(run_id: str, path: str, text: str) -> bool:
    """Replace a text file a run already logged, in its local artifact folder, and add it to the
    run's louped.edited tag; False when the run or file is not there. Refused for other types, for
    JSON, JSONL or TOML that does not parse, and for a store that is not local."""
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"{path}: a path inside the run's artifacts")
    if not path.lower().endswith(EDITABLE):
        raise ValueError(f"{path}: only text files are edited here ({', '.join(EDITABLE)})")
    _check(path, text)
    client = _client()
    if client is None:
        return False
    try:
        run = client.get_run(run_id.removeprefix(PREFIX))
    except Exception as exc:
        if _missing(exc):
            return False
        raise
    uri = run.info.artifact_uri or ""
    if not uri.startswith("file://") and not uri.startswith("/"):
        raise ValueError(f"{run_id}'s artifacts are not on this machine ({uri})")
    # realpath and a prefix check: the guard code scanning recognizes for a path from a request
    folder = os.path.realpath(uri.removeprefix("file://"))
    target = os.path.realpath(os.path.join(folder, rel))
    if not target.startswith(folder + os.sep) or not os.path.isfile(target):
        return False
    with open(target, "w", encoding="utf-8") as out:
        out.write(text)
    edited = {p for p in run.data.tags.get(EDITED, "").split(",") if p} | {rel.as_posix()}
    client.set_tag(run.info.run_id, EDITED, ",".join(sorted(edited)))
    return True


def _check(path: str, text: str) -> None:
    """A structured file must still parse: an edit never leaves a run's data unreadable."""
    kind = path.lower().rsplit(".", 1)[-1]
    try:
        if kind == "json":
            json.loads(text)
        elif kind in ("jsonl", "ndjson"):
            for n, line in enumerate(text.splitlines(), 1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"line {n}: {exc}") from exc
        elif kind == "toml":
            tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{path} is not valid {kind}: {exc}") from exc


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
