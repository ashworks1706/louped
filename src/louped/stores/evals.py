"""Runs read from Inspect eval logs."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from inspect_ai.event import ModelEvent
from inspect_ai.log import (
    EvalLog,
    list_eval_logs,
    read_eval_log,
    read_eval_log_sample,
    read_eval_log_sample_summaries,
    read_eval_log_samples,
)
from inspect_ai.scorer import Score as InspectScore

from louped.core import experiments_dir, home, logs_dir
from louped.core.judges import pair_key, request_text
from louped.stores import degeneracy
from louped.stores.types import (
    Degenerate,
    Message,
    ModelInput,
    Reading,
    RunDetail,
    RunSummary,
    SampleDetail,
    SampleSummary,
    Score,
    ToolCall,
)
from louped.stores.values import GRADES, flatten, text, to_float

log = logging.getLogger(__name__)

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


def eval_logs() -> list[tuple[Path, EvalLog]]:
    root = logs_dir()
    if not root.is_dir():
        return []
    found: list[tuple[Path, EvalLog]] = []
    for info in list_eval_logs(str(root)):
        path = Path(info.name.removeprefix("file://"))
        try:
            found.append((path, _header(str(path), path.stat().st_mtime)))
        except Exception as exc:  # an unreadable or half-written log is skipped, not fatal
            log.warning("skipping eval log %s: %s", path, exc)
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


@lru_cache(maxsize=4)
def _hosts(path: str, mtime: float) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hosts() -> dict[str, str]:
    """Where imported eval runs ran, by run id: Inspect logs carry no host of their own."""
    path = home() / "hosts.json"
    return _hosts(str(path), path.stat().st_mtime) if path.exists() else {}


def _name(log: EvalLog) -> str:
    """The task, and for a grid's eval the cell it ran: `refusal · ablate · seed 1`."""
    task = log.eval.task_display_name or log.eval.task
    cell = (log.eval.metadata or {}).get("cell")
    return f"{task} · {cell}" if cell else task


def _summary(path: Path, log: EvalLog) -> RunSummary:
    samples = log.results.total_samples if log.results else None
    if log.status == "started":
        samples = _done(str(path), path.stat().st_mtime)
    planned = len(log.eval.dataset.sample_ids or []) or log.eval.dataset.samples
    return RunSummary(
        id=PREFIX + log.eval.eval_id,
        kind="eval",
        name=_name(log),
        experiment=experiment_of(log),
        status=log.status,
        created=log.eval.created,  # type: ignore[arg-type]
        model=log.eval.model,
        metrics=_metrics(log),
        samples=samples,
        total=planned * (log.eval.config.epochs or 1) if planned else None,
        host=hosts().get(PREFIX + log.eval.eval_id),
    )


def list_runs() -> list[RunSummary]:
    return [_summary(path, log) for path, log in eval_logs()]


def _find(run_id: str) -> tuple[Path, EvalLog] | None:
    eval_id = run_id.removeprefix(PREFIX)
    return next(((p, log) for p, log in eval_logs() if log.eval.eval_id == eval_id), None)


def log_of(run_id: str) -> tuple[Path, EvalLog] | None:
    """An eval run's log file and header, None for a run that is not an Inspect eval."""
    return _find(run_id) if run_id.startswith(PREFIX) else None


def answers(run_id: str) -> dict[str, tuple[str, str]] | None:
    """Each sample the run answered without error, by id (id#epoch past the first epoch): its
    request in full and the model's final answer; None for a run that is not an Inspect eval."""
    found = log_of(run_id)
    if found is None:
        return None
    out: dict[str, tuple[str, str]] = {}
    for s in read_eval_log_samples(str(found[0])):
        if s.error is None:  # what louped judge pairs too (louped.inspect_ext.judge.pairs)
            out[pair_key(s.id, s.epoch)] = (request_text(s.input), s.output.completion)
    return out


def judge_runs(a: str, b: str) -> list[str]:
    """The judge runs (louped judge) of b against a, newest first."""
    found = [(p, log) for p, log in eval_logs()
             if (log.eval.metadata or {}).get("a") == a and (log.eval.metadata or {}).get("b") == b
             and log.eval.task.endswith("judge")]  # fmt: skip
    found.sort(key=lambda f: f[1].eval.created, reverse=True)
    return [f"{PREFIX}{log.eval.eval_id}" for _, log in found]


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
    # what the run was started with beyond its task: a judge's runs and file, a grid's cell
    params |= {f"meta.{k}": v for k, v in _stringify(log.eval.metadata or {}).items()}
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


@lru_cache(maxsize=16)
def _degenerate(path: str, mtime: float) -> dict[tuple[str, int], list[Degenerate]]:
    """Each finished log's samples' degeneracy flags, by id and epoch, read once per change."""
    samples = read_eval_log_samples(
        path, all_samples_required=False, resolve_attachments=True, exclude_fields={"events"}
    )
    return {
        (str(s.id), s.epoch): degeneracy.flags([(m.role, m.text) for m in s.messages])
        for s in samples
    }


def list_samples(run_id: str) -> list[SampleSummary] | None:
    found = _find(run_id)
    if found is None:
        return None
    path, log = found
    flags = None if log.status == "started" else _degenerate(str(path), path.stat().st_mtime)
    summaries = read_eval_log_sample_summaries(str(path))
    names = readers(s.scores or {} for s in summaries)
    out: list[SampleSummary] = []
    for s in summaries:
        scores: dict[str, float | None] = {}
        for name, score in (s.scores or {}).items():
            scores |= flatten(name, score.value)
        read = {n: _reading(sc) for n, sc in (s.scores or {}).items() if n in names}
        out.append(
            SampleSummary(
                id=str(s.id),
                epoch=s.epoch,
                input=text(s.input, 240),
                target=text(s.target, 120),
                scores=scores,
                error=s.error,
                degenerate=None if flags is None else flags.get((str(s.id), s.epoch), []),
                readings=read,
                disagree=len(names) > 1 and disagree([scores.get(n) for n in read]),
            )
        )
    return out


def _reads(score: InspectScore) -> bool:
    """A score that reads a verdict: it records the rule that read it, or grades C/I/P/N."""
    graded = isinstance(score.value, str) and score.value in GRADES
    return graded or "read_by" in (score.metadata or {})


def readers(samples: Iterable[dict[str, InspectScore]]) -> list[str]:
    """The scores that read a verdict on any of the samples, by name."""
    return sorted({n for scores in samples for n, sc in scores.items() if _reads(sc)})


def disagree(values: list[float | None]) -> bool:
    """Readers disagree when two of them give the sample different values; a reader with no
    value says nothing."""
    return len({v for v in values if v is not None}) > 1


def _reading(score: InspectScore) -> Reading:
    meta = score.metadata or {}
    rule, matched = meta.get("read_by"), meta.get("matched")
    return Reading(read_by=None if rule is None else str(rule),
                   matched=None if matched is None else str(matched))  # fmt: skip


def _input(event: ModelEvent) -> ModelInput:
    """What a model call read: reported by louped/'s provider, else only its model."""
    meta = event.output.metadata or {}
    if "rendered_input" not in meta:
        return ModelInput(model=event.model)
    return ModelInput(model=event.model, text=meta["rendered_input"],
                      tokens=meta.get("rendered_tokens"),
                      special_tokens=meta.get("special_tokens") or [],
                      tokenizer=meta.get("tokenizer"),
                      chat_template=meta.get("chat_template"))  # fmt: skip


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
            **(_reading(score).model_dump() if "read_by" in (score.metadata or {}) else {}),
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
        inputs=[_input(e) for e in s.events if isinstance(e, ModelEvent)],
    )
