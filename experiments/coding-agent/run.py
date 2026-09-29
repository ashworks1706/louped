"""The coding agent under several conditions as one grid: base against steered, two local models,
or any OpenAI-compatible endpoint.

    uv run --all-extras python experiments/coding-agent/run.py --model Qwen/Qwen2.5-1.5B-Instruct \\
        --conditions '{"base": {}, "steered": {"interventions": {"kind": "steer", ...}}}'
    uv run --all-extras python experiments/coding-agent/run.py \\
        --conditions '{"local": {"model": "openai-api/local/qwen"}}'   # LOCAL_BASE_URL and _API_KEY
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import tyro

sys.path.insert(0, str(Path(__file__).parent))
from task import coding_agent

from loupe.grid import grid


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    """The loupe/ model a condition runs unless it names another Inspect model."""
    conditions: str = '{"base": {}}'
    """JSON: condition name to loupe/ provider args, or to {"model": <any Inspect model>, ...}."""
    benchmark: str = "builtin"
    metric: str = "verify/accuracy"
    """The grid's metric as scorer/metric, e.g. tool_errors/mean."""
    held: str | None = None
    seeds: int = 1


def main(args: Args) -> None:
    conditions = json.loads(args.conditions)
    task = coding_agent(args.benchmark)
    run = grid({args.benchmark: task}, args.model, conditions, args.metric, list(range(args.seeds)),
               held=args.held, experiment="coding-agent")  # fmt: skip
    print(json.dumps({"grid": run}))


if __name__ == "__main__":
    main(tyro.cli(Args))
