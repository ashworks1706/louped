"""Leaderboards: each eval task's finished runs by score, and the speed benchmarks (louped bench)
by throughput.

An eval run belongs to the task it ran: a registered task by its name (inspect_evals/<name>,
louped/<name>), a project task by its file and function (experiments/<name>/task.py@fn, what
Launch and stores.catalog call it). Its score is its first scorer's accuracy (else its mean, else
its first metric). A speed benchmark is a `louped bench` run, read from the figures it logs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from inspect_ai.log import EvalLog
from pydantic import BaseModel

from louped.core import experiments_dir
from louped.stores import evals, mlflow_runs, views
from louped.stores.types import LineView, TableView
from louped.stores.values import to_float

#: The metrics a score is read from, first found first.
HEADLINE = ("accuracy", "mean")
#: How `louped bench` names its runs and figures (louped.bench).
BENCH_RUN = "bench · "
THROUGHPUT, PREFILL, MEMORY, WEIGHTS = (
    "Throughput under load",
    "Prefill by context",
    "Memory by context",
    "Weights",
)


class Entry(BaseModel):
    """One finished eval run of a task."""

    run: str
    model: str | None
    #: The headline score: metric of the run's first scorer.
    score: float | None
    #: scorer/metric the score is.
    metric: str | None
    samples: int | None
    created: datetime | None


class SpeedRow(BaseModel):
    """One weight format of one `louped bench` run."""

    run: str
    model: str | None
    #: The weight format: as saved, or the quantization it was loaded with.
    setting: str
    device: str | None = None
    weights_mib: float | None = None
    #: The most tokens per second over a batch, and the batch size it was reached at.
    throughput: float | None = None
    batch: int | None = None
    #: Milliseconds to read the longest prompt measured, and its length in tokens.
    prefill_ms: float | None = None
    context: int | None = None
    #: Peak GPU memory reading that prompt (CUDA only).
    peak_mib: float | None = None
    created: datetime | None = None
    #: The fastest setting of this model over every run.
    best: bool = False


def task_key(log: EvalLog) -> str:
    """The task an eval log ran, as stores.catalog names it."""
    task, file = log.eval.task, log.eval.task_file
    if "/" in task or not file:
        return task
    path = Path(file).resolve()
    root = experiments_dir().resolve().parent
    return f"{path.relative_to(root).as_posix()}@{task}" if path.is_relative_to(root) else task


def _headline(log: EvalLog) -> tuple[str, float] | None:
    scores = log.results.scores if log.results else []
    if not scores:
        return None
    first = scores[0]
    names = [n for n in HEADLINE if n in first.metrics] or list(first.metrics)
    for name in names:
        value = to_float(first.metrics[name].value)
        if value is not None:
            return f"{first.name}/{name}", value
    return None


def boards() -> dict[str, list[Entry]]:
    """Every task's finished eval runs, best score first (newest first among equals)."""
    out: dict[str, list[Entry]] = defaultdict(list)
    for _, log in evals.eval_logs():
        if log.status != "success":
            continue
        found = _headline(log)
        out[task_key(log)].append(Entry(
            run=evals.PREFIX + log.eval.eval_id, model=log.eval.model,
            score=found[1] if found else None, metric=found[0] if found else None,
            samples=log.results.total_samples if log.results else None,
            created=log.eval.created,  # type: ignore[arg-type]
        ))  # fmt: skip
    for entries in out.values():
        entries.sort(key=lambda e: e.created.timestamp() if e.created else 0, reverse=True)
        entries.sort(key=lambda e: -e.score if e.score is not None else float("inf"))
    return dict(out)


def _last(view: LineView | None, series: str) -> tuple[float, int] | None:
    """A line's last point of series: (y, x)."""
    ys = view.series.get(series) if view else None
    return (ys[-1], int(view.x[len(ys) - 1])) if view and ys else None


def speed() -> list[SpeedRow]:
    """Each weight format of each `louped bench` run, newest first; best marks the fastest
    setting of each model."""
    rows: list[SpeedRow] = []
    for run in mlflow_runs.list_runs():
        if not run.name.startswith(BENCH_RUN):
            continue
        figures = {v.view.title: v.view for v in views.list_views(run.id) or []}
        load, pre, mem, size = (figures.get(t) for t in (THROUGHPUT, PREFILL, MEMORY, WEIGHTS))
        load = load if isinstance(load, LineView) else None
        pre = pre if isinstance(pre, LineView) else None
        mem = mem if isinstance(mem, LineView) else None
        weights = {str(r[0]): r for r in size.rows} if isinstance(size, TableView) else {}
        named: list[str] = [*weights, *(load.series if load else [])]
        for setting in dict.fromkeys(named):
            row = SpeedRow(run=run.id, model=run.model or run.name.removeprefix(BENCH_RUN),
                           setting=setting, created=run.created)  # fmt: skip
            if setting in weights:
                cells = weights[setting]
                row.weights_mib = to_float(cells[1]) if len(cells) > 1 else None
                row.device = str(cells[3]) if len(cells) > 3 else None
            ys = load.series.get(setting) if load else None
            if load and ys:
                best = max(range(len(ys)), key=ys.__getitem__)
                row.throughput, row.batch = ys[best], int(load.x[best])
            if read := _last(pre, setting):
                row.prefill_ms, row.context = read
            if read := _last(mem, setting):
                row.peak_mib = read[0]
            rows.append(row)
    top: dict[str, SpeedRow] = {}
    for row in rows:
        key = row.model or ""
        if row.throughput is not None and (
            key not in top or row.throughput > (top[key].throughput or 0)
        ):
            top[key] = row
    for row in top.values():
        row.best = True
    return sorted(rows, key=lambda r: r.created.timestamp() if r.created else 0, reverse=True)
