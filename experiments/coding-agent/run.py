"""The coding agent under several conditions as one grid: base against steered, two local models,
or any OpenAI-compatible endpoint; or scripted, to check the sandbox and scorers offline.

    uv run --all-extras python experiments/coding-agent/run.py --model Qwen/Qwen2.5-1.5B-Instruct \\
        --conditions '{"base": {}, "steered": {"interventions": {"kind": "steer", ...}}}'
    uv run --all-extras python experiments/coding-agent/run.py \\
        --conditions '{"local": {"model": "openai-api/local/qwen"}}'   # LOCAL_BASE_URL and _API_KEY
    uv run --all-extras python experiments/coding-agent/run.py --scripted   # Docker, a mock model
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import tyro
from inspect_ai.model import ModelOutput, ModelUsage

sys.path.insert(0, str(Path(__file__).parent))
from task import PROBLEMS, coding_agent

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
    scripted: bool = False
    """Two mock agents, one that tests its code and one whose calls fail: checks Docker, scorers."""


def scripted(careful: bool):
    """A mock agent. Careful: runs its solution in python, then submits it. Sloppy: calls python
    with a wrong argument name, then submits a stub."""

    def respond(messages, tools, tool_choice, config) -> ModelOutput:
        ask = next(m.text for m in messages if m.role == "user")
        problem = next(p for p in PROBLEMS if p["prompt"] in ask)
        name = problem["entry_point"]
        stub = f"def {name}(*args):\n    return None\n"
        code = problem["canonical_solution"] if careful else stub
        if not any(m.role == "tool" for m in messages):
            args = {"code": f"{code}print({name}.__name__, 'ok')"} if careful else {"src": code}
            out = ModelOutput.for_tool_call("mockllm/model", "python", args, content="")
        else:
            out = ModelOutput.for_tool_call("mockllm/model", "submit", {"answer": code}, content="")
        out.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
        return out

    return respond


def main(args: Args) -> None:
    conditions = json.loads(args.conditions)
    if args.scripted:
        conditions = {
            name: {"model": "mockllm/model", "custom_outputs": scripted(name == "careful")}
            for name in ("careful", "sloppy")
        }
    task = coding_agent(args.benchmark)
    run = grid({args.benchmark: task}, args.model, conditions, args.metric, list(range(args.seeds)),
               held=args.held, experiment="coding-agent")  # fmt: skip
    print(json.dumps({"grid": run}))


if __name__ == "__main__":
    main(tyro.cli(Args))
