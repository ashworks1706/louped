"""The sandbox task through the loupe/ provider, base against steered, as one grid.

    uv run --all-extras python experiments/agent-sandbox/run.py --model Qwen/Qwen2.5-1.5B-Instruct
    uv run --all-extras python experiments/agent-sandbox/run.py \\
        --steer '{"kind": "steer", "vector": "<a saved vector>", "alpha": 4}'
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tyro

sys.path.insert(0, str(Path(__file__).parent))
from task import agent_sandbox

from loupe.grid import grid


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    steer: str | None = None
    """A Steer spec as JSON, run beside the base."""


def main(args: Args) -> None:
    conditions: dict[str, dict[str, Any]] = {"base": {}}
    if args.steer:
        conditions["steered"] = {"interventions": json.loads(args.steer)}
    run = grid({"sandbox": agent_sandbox()}, args.model, conditions, "includes/accuracy",
               experiment="agent-sandbox")  # fmt: skip
    print(json.dumps({"grid": run}))


if __name__ == "__main__":
    main(tyro.cli(Args))
