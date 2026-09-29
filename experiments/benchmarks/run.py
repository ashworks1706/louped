"""Standard benchmarks from inspect_evals on any model or endpoint, one grid per benchmark: every
condition against the first, sample by sample, with paired intervals.

    uv run --all-extras python experiments/benchmarks/run.py --benchmarks squad bfcl --limit 50
    uv run --all-extras python experiments/benchmarks/run.py --benchmarks drop \\
        --model qwen2.5:7b-instruct --base-url http://localhost:11434/v1
    uv run --all-extras python experiments/benchmarks/run.py --benchmarks truthfulqa \\
        --conditions '{"ablated": {"interventions": {"kind": "ablate", "vector": "<v>"}}}'

Each benchmark is read by its own score (BENCHMARKS); --metric overrides it for all.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import Any

import tyro
from inspect_ai import Task, task_with
from inspect_ai.model import GenerateConfig

from loupe.grid import endpoint, grid

#: name: (inspect_evals task, the score the grid reads, what it measures)
BENCHMARKS = {
    "squad": ("inspect_evals.squad:squad", "f1/mean",
              "reading comprehension, some questions unanswerable from the passage"),
    "drop": ("inspect_evals.drop:drop", "f1/mean", "discrete reasoning over a paragraph"),
    "bfcl": ("inspect_evals.bfcl:bfcl", "bfcl_scorer/accuracy", "function calling"),
    "truthfulqa": ("inspect_evals.truthfulqa:truthfulqa", "choice/accuracy",
                   "answers that avoid common misconceptions"),
    "gsm8k": ("inspect_evals.gsm8k:gsm8k", "match/accuracy", "grade-school maths"),
    "tau2-retail": ("inspect_evals.tau2:tau2_retail", "retail_scorer/accuracy",
                    "an agent serving a simulated customer under a store's policy, with tools"),
}  # fmt: skip

#: Benchmarks with a simulated user, played by the model in Inspect's "user" role.
SIMULATED_USER = {"tau2-retail"}


def benchmark(name: str, limit: int | None, max_tokens: int) -> Task:
    """The benchmark's task, cut to its first limit samples, decoding greedily."""
    if name not in BENCHMARKS:
        raise SystemExit(f"unknown benchmark {name!r}; known: {', '.join(BENCHMARKS)}")
    module, _, fn = BENCHMARKS[name][0].partition(":")
    task = getattr(importlib.import_module(module), fn)()
    dataset = task.dataset[:limit] if limit else task.dataset
    return task_with(task, dataset=dataset,
                     config=GenerateConfig(max_tokens=max_tokens, temperature=0))  # fmt: skip


@dataclass
class Args:
    benchmarks: list[str] = field(default_factory=lambda: ["squad"])
    """Any of squad, drop, bfcl, truthfulqa, gsm8k, tau2-retail."""
    model: str = "loupe/Qwen/Qwen2.5-0.5B-Instruct"
    """The first condition: any Inspect model, or with --base-url the id a server serves."""
    base_url: str | None = None
    api_key: str | None = None
    """The server's key, if it checks one; never logged."""
    conditions: str = "{}"
    """JSON: more conditions against the first, each a name to loupe/ provider args, or to
    {"model": ..., "base_url": ..., "api_key": ...} for any other model or endpoint."""
    limit: int | None = 50
    """Samples per benchmark; None runs all."""
    max_tokens: int = 512
    metric: str | None = None
    """The score every grid reads, instead of each benchmark's own."""
    user_model: str | None = None
    """Who plays the simulated user in tau2 benchmarks: any Inspect model; by default --model."""
    seeds: int = 1


def main(args: Args) -> None:
    base = endpoint(args.model, args.base_url, args.api_key)
    extra: dict[str, dict[str, Any]] = json.loads(args.conditions)
    conditions = {
        "base": base,
        **{name: ({**base, **c} if "model" not in c else c) for name, c in extra.items()},
    }
    for name in args.benchmarks:
        task = benchmark(name, args.limit, args.max_tokens)
        metric = args.metric or BENCHMARKS[name][1]
        runs = conditions
        if name in SIMULATED_USER:
            user = args.user_model or base["model"]
            runs = {c: {**spec, "roles": {"user": user}} for c, spec in conditions.items()}
        run = grid({name: task}, args.model, runs, metric, list(range(args.seeds)),
                   experiment="benchmarks")  # fmt: skip
        print(json.dumps({"benchmark": name, "grid": run}))


if __name__ == "__main__":
    main(tyro.cli(Args))
