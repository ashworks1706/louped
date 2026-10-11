"""Benchmarks, on the Benchmarks page of Behavior and of Efficiency.

Behavior: every eval task Launch runs (the project's, its Hub benchmarks, inspect_evals'), each
with its finished runs as a leaderboard (louped.stores.leaderboards). A Hub dataset becomes a
benchmark with a field mapping kept in louped.toml ([benchmarks.<name>], louped.core.benchmarks):
the mapping is checked against the dataset's splits and features when the dataset viewer
answers, and the benchmark is then the task louped/<name>, launched like any other.

Efficiency: the speed benchmarks, `louped bench` runs, by model and weight format.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from louped.core.benchmarks import NAME, Benchmark, benchmarks, task_name
from louped.server import datasets, hub
from louped.server.launch import require_json
from louped.stores import leaderboards
from louped.stores.catalog import EvalTask, eval_tasks
from louped.stores.leaderboards import Entry, SpeedRow


class BenchmarkRow(BaseModel):
    """One eval task with its leaderboard's size and top run."""

    task: EvalTask
    #: Finished runs of it.
    runs: int
    best: Entry | None = None
    #: A Hub benchmark's field mapping.
    spec: Benchmark | None = None


class Leaderboard(BaseModel):
    #: The task as Launch lists it; None for runs of a task no longer found.
    task: EvalTask | None
    spec: Benchmark | None = None
    #: Its finished runs, best score first.
    entries: list[Entry]


class BenchmarkRequest(Benchmark):
    name: str = Field(pattern=NAME)


class AddedBenchmark(BaseModel):
    benchmark: BenchmarkRow
    #: Whether the mapping was checked against the dataset's splits and features.
    checked: bool
    #: Why it was not checked, when it was not.
    note: str | None = None


def _specs() -> dict[str, Benchmark]:
    return {task_name(n): b for n, b in benchmarks().items()}


def rows() -> list[BenchmarkRow]:
    """Every eval task, those with runs first (most runs first), then as Launch lists them."""
    boards, specs = leaderboards.boards(), _specs()
    found = [BenchmarkRow(task=t, runs=len(boards.get(t.task, [])),
                          best=next(iter(boards.get(t.task, [])), None), spec=specs.get(t.task))
             for t in eval_tasks()]  # fmt: skip
    return sorted(found, key=lambda r: -r.runs)


def resolve(task: str, tasks: list[EvalTask]) -> str:
    """A task as written (experiments/x/task.py@fn, louped/gsm8k, inspect_evals/gsm8k), or a
    Hub benchmark's or inspect_evals' bare name."""
    names = {t.task for t in tasks}
    return next((t for t in (task, task_name(task), f"inspect_evals/{task}") if t in names), task)


def board(task: str) -> Leaderboard:
    tasks = eval_tasks()
    key = resolve(task, tasks)
    entries = leaderboards.boards().get(key, [])
    found = next((t for t in tasks if t.task == key), None)
    if found is None and not entries:
        raise HTTPException(404, f"no eval task {task} and no runs of it")
    return Leaderboard(task=found, spec=_specs().get(key), entries=entries)


def check(spec: Benchmark) -> str | None:
    """ValueError when the dataset viewer shows the mapping is wrong (no such config, split or
    field); the reason it was not checked when the viewer cannot answer; None when it holds."""
    try:
        splits = datasets.hub_splits(spec.dataset)
    except datasets.ViewerError as exc:
        return f"not checked against the dataset: {exc}"
    configs = list(dict.fromkeys(s.config for s in splits))
    if not configs:
        return "not checked: the dataset viewer lists no splits for it"
    if spec.config is None and len(configs) > 1:
        raise ValueError(f"{spec.dataset} has configs {', '.join(configs)}: name one")
    config = spec.config or configs[0]
    if config not in configs:
        raise ValueError(f"{spec.dataset} has no config {config}; it has {', '.join(configs)}")
    mine = [s.split for s in splits if s.config == config]
    if spec.split not in mine:
        raise ValueError(f"{spec.dataset} ({config}) has no split {spec.split}; it has "
                         f"{', '.join(mine)}")  # fmt: skip
    try:
        features = datasets.hub_features(spec.dataset, config, spec.split)
    except datasets.ViewerError as exc:
        return f"fields not checked: {exc}"
    names = [f.name for f in features]
    missing = [f for f in (spec.input, spec.target, spec.choices) if f and f not in names]
    if missing:
        raise ValueError(f"{spec.dataset} has no field {', '.join(missing)}; its fields are "
                         f"{', '.join(names)}")  # fmt: skip
    return None


def add(req: BenchmarkRequest) -> AddedBenchmark:
    """Check the mapping, then keep it as [benchmarks.<name>] in louped.toml, replacing one of
    that name."""
    spec = Benchmark.model_validate(req.model_dump(exclude={"name"}))
    note = check(spec)
    values = spec.model_dump()
    hub.write_toml(f"benchmarks.{req.name}", {k: values[k] for k in Benchmark.model_fields})
    task = task_name(req.name)
    found = next(r for r in rows() if r.task.task == task)
    return AddedBenchmark(benchmark=found, checked=note is None, note=note)


def router(editing: Callable[[], None]) -> APIRouter:
    api = APIRouter(prefix="/api/benchmarks")

    @api.get("")
    def list_benchmarks() -> list[BenchmarkRow]:
        """Every eval task with the size and top of its leaderboard, those with runs first."""
        try:
            return rows()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.get("/board")
    def leaderboard(task: str) -> Leaderboard:
        """One eval task's finished runs, best score first."""
        try:
            return board(task)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.get("/speed")
    def speed() -> list[SpeedRow]:
        """Each weight format of each `louped bench` run, newest first; best marks each
        model's fastest."""
        return leaderboards.speed()

    @api.post("", dependencies=[Depends(require_json)])
    def add_benchmark(req: BenchmarkRequest) -> AddedBenchmark:
        """A Hub dataset as a benchmark: checked against its splits and features when the
        dataset viewer answers, then kept in louped.toml and listed as the task louped/<name>."""
        editing()
        try:
            return add(req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return api
