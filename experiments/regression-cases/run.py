"""A file of regression cases against any model, endpoint or agent, as one grid: every condition
against the first, case by case, with paired intervals.

    uv run --all-extras python experiments/regression-cases/run.py --cases my-cases.jsonl
    uv run --all-extras python experiments/regression-cases/run.py --cases my-cases.jsonl \\
        --model my-agent --base-url http://localhost:8080/v1 --agent
    uv run --all-extras python experiments/regression-cases/run.py --cases my-cases.jsonl \\
        --conditions '{"tuned": {"model": "loupe/my-finetune"}}'

The case format and its expectations are in loupe.inspect_ext.cases; example.jsonl shows each.
With --agent the endpoint is an agent that runs its own tools and reports them in a `trace` field
(loupe.inspect_ext.agent); without, tool expectations can only be met by a model that calls tools
inside Inspect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tyro
from inspect_ai import task_with
from inspect_ai.model import GenerateConfig

from loupe.grid import endpoint, grid
from loupe.inspect_ext import cases

EXAMPLE = Path(__file__).with_name("example.jsonl")


@dataclass
class Args:
    cases: Path = EXAMPLE
    """JSONL of {"id", "input", "expect": {...}}."""
    model: str = "loupe/Qwen/Qwen2.5-0.5B-Instruct"
    """The first condition: any Inspect model, or with --base-url the id a server serves."""
    base_url: str | None = None
    api_key: str | None = None
    """The server's key, if it checks one; never logged."""
    agent: bool = False
    """The endpoint is an agent that runs its own tools and reports them."""
    conditions: str = "{}"
    """JSON: more conditions against the first, each a name to loupe/ provider args, or to
    {"model": ..., "base_url": ..., "api_key": ...} for any other model or endpoint."""
    max_tokens: int = 512
    seeds: int = 1


def main(args: Args) -> None:
    base = endpoint(args.model, args.base_url, args.api_key, agent=args.agent)
    extra: dict[str, dict[str, Any]] = json.loads(args.conditions)
    conditions = {
        "base": base,
        **{name: ({**base, **c} if "model" not in c else c) for name, c in extra.items()},
    }
    task = task_with(cases(args.cases), config=GenerateConfig(max_tokens=args.max_tokens))
    run = grid({args.cases.stem: task}, args.model, conditions, "expectations/mean",
               list(range(args.seeds)), experiment="regression-cases")  # fmt: skip
    print(json.dumps({"grid": run}))


if __name__ == "__main__":
    main(tyro.cli(Args))
