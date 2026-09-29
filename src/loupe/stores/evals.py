"""Runs read from Inspect eval logs."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from inspect_ai.log import (
    EvalLog,
    list_eval_logs,
    read_eval_log,
    read_eval_log_sample,
    read_eval_log_sample_summaries,
)

from loupe.core import experiments_dir, logs_dir
from loupe.stores.types import (
    Message,
    RunDetail,
    RunSummary,
    SampleDetail,
    SampleSummary,
    Score,
    ToolCall,
)
from loupe.stores.values import flatten, text, to_float

PREFIX = "e-"


@lru_cache(maxsize=512)
def _header(path: str, mtime: float) -> EvalLog:
    """A log's header, cached until the file changes."""
    return read_eval_log(path, header_only=True)


@lru_cache(maxsize=64)
def _done(path: str, mtime: float) -> int:
    """How many samples a running log has written so far."""
    try:
        return len(read_eval_log_sample_summaries(path))
    except Exception:  # the log is mid-write; the next read will see it
        return 0


def _logs() -> list[tuple[Path, EvalLog]]:
    root = logs_dir()
    if not root.is_dir():
        return []
    found: list[tuple[Path, EvalLog]] = []
    for info in list_eval_logs(str(root)):
        path = Path(info.name.removeprefix("file://"))
        try:
            found.append((path, _header(str(path), path.stat().st_mtime)))
        except Exception:  # an unreadable or half-written log is skipped, not fatal
            continue
    return found


def experiment_of(log: EvalLog) -> str | None:
    """The experiments/ folder a log answers: from an experiment tag, else its task file's path."""
    for tag in log.eval.tags or []:
        if tag.startswith("experiment:"):
            return tag.split(":", 1)[1]
    task_file = log.eval.task_file
    if not task_file:
        return None
    parts = Path(task_file).resolve().parts
    root = experiments_dir().parts
    if parts[: len(root)] == root and len(parts) > len(root):
        return parts[len(root)]
    return None


def _metrics(log: EvalLog) -> dict[str, float]:
    out: dict[str, float] = {}
    for score in log.results.scores if log.results else []:
        for metric in score.metrics.values():
            value = to_float(metric.value)
            if value is not None:
                out[f"{score.name}/{metric.name}"] = value
    return out


def _summary(path: Path, log: EvalLog) -> RunSummary:
    samples = log.results.total_samples if log.results else None
    if log.status == "started":
        samples = _done(str(path), path.stat().st_mtime)
    planned = len(log.eval.dataset.sample_ids or []) or log.eval.dataset.samples
    return RunSummary(
        id=PREFIX + log.eval.eval_id,
        kind="eval",
        name=log.eval.task_display_name or log.eval.task,
        experiment=experiment_of(log),
        status=log.status,
        created=log.eval.created,  # type: ignore[arg-type]
        model=log.eval.model,
        metrics=_metrics(log),
        samples=samples,
        total=planned * (log.eval.config.epochs or 1) if planned else None,
    )


def list_runs() -> list[RunSummary]:
    return [_summary(path, log) for path, log in _logs()]


def _find(run_id: str) -> tuple[Path, EvalLog] | None:
    eval_id = run_id.removeprefix(PREFIX)
    return next(((p, log) for p, log in _logs() if log.eval.eval_id == eval_id), None)


def log_mtime(run_id: str) -> float | None:
    """When the run's log last changed, None for an unknown run: a cache key for derived results."""
    found = _find(run_id)
    return found[0].stat().st_mtime if found else None


def _stringify(values: dict[str, Any] | None) -> dict[str, str]:
    return {k: str(v) for k, v in (values or {}).items()}


def get_run(run_id: str) -> RunDetail | None:
    found = _find(run_id)
    if found is None:
        return None
    path, log = found
    params = {f"task.{k}": v for k, v in _stringify(log.eval.task_args).items()}
    params |= {f"model.{k}": v for k, v in _stringify(log.eval.model_args).items()}
    params |= {
        f"generate.{k}": str(v)
        for k, v in log.eval.model_generate_config.model_dump(exclude_none=True).items()
    }
    return RunDetail(
        **_summary(path, log).model_dump(),
        params=params,
        tags={t: "" for t in log.eval.tags or []},
        history={},
        artifacts=[],
        scorers=[s.name for s in log.results.scores] if log.results else [],
        error=log.error.message if log.error else None,
        log=path.relative_to(logs_dir()).as_posix(),
    )


def list_samples(run_id: str) -> list[SampleSummary] | None:
    found = _find(run_id)
    if found is None:
        return None
    path, _ = found
    out: list[SampleSummary] = []
    for s in read_eval_log_sample_summaries(str(path)):
        scores: dict[str, float | None] = {}
        for name, score in (s.scores or {}).items():
            scores |= flatten(name, score.value)
        out.append(
            SampleSummary(
                id=str(s.id),
                epoch=s.epoch,
                input=text(s.input, 240),
                target=text(s.target, 120),
                scores=scores,
                error=s.error,
            )
        )
    return out


def _message(m: Any) -> Message:
    calls = [
        ToolCall(id=c.id, function=c.function, parse_error=c.parse_error,
                 arguments=json.dumps(c.arguments, indent=2, default=str))
        for c in getattr(m, "tool_calls", None) or []
    ]  # fmt: skip
    error = getattr(m, "error", None)
    return Message(role=m.role, text=m.text, tool_calls=calls,
                   tool_call_id=getattr(m, "tool_call_id", None),
                   function=getattr(m, "function", None),
                   error=f"{error.type}: {error.message}" if error else None)  # fmt: skip


def get_sample(run_id: str, sample_id: str, epoch: int) -> SampleDetail | None:
    found = _find(run_id)
    if found is None:
        return None
    path, _ = found
    key: int | str = int(sample_id) if sample_id.isdigit() else sample_id
    try:
        s = read_eval_log_sample(str(path), id=key, epoch=epoch)
    except (IndexError, KeyError, ValueError):
        return None
    scores = [
        Score(
            name=name,
            value=to_float(score.value),
            raw=str(score.value),
            answer=score.answer,
            explanation=score.explanation,
        )
        for name, score in (s.scores or {}).items()
    ]
    return SampleDetail(
        id=str(s.id),
        epoch=s.epoch,
        target=text(s.target),
        messages=[_message(m) for m in s.messages],
        scores=scores,
        metadata=_stringify(s.metadata),
        error=s.error.message if s.error else None,
    )
