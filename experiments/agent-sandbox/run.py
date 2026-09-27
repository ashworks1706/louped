"""The sandbox task, base against steered, through the loupe/ provider; or scripted, to check the
Docker plumbing and the tool-call transcripts without a model.

    uv run --all-extras python experiments/agent-sandbox/run.py --model Qwen/Qwen2.5-1.5B-Instruct
    uv run --all-extras python experiments/agent-sandbox/run.py --scripted   # Docker, a toy model

Scripted: the tiny offline model through the loupe/ provider, its replies replaced by the right
tool calls, so Docker, the provider's tool-call parsing and the transcripts are checked without
downloading a model.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import tyro
from inspect_ai import eval
from inspect_ai.model import get_model

sys.path.insert(0, str(Path(__file__).parent))
from task import SECRETS, agent_sandbox

from loupe.core import logs_dir


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    steer: str | None = None
    """A Steer spec as JSON, run beside the base."""
    scripted: bool = False
    """The tiny offline model with scripted tool calls: checks Docker, parsing and transcripts."""


def scripted() -> str:
    from loupe.core import home
    from loupe.inspect_ext import provider
    from loupe.models.tiny import tiny

    lm = tiny()
    lm._model.save_pretrained(home() / "models" / "tiny-scripted")
    lm.tokenizer.save_pretrained(home() / "models" / "tiny-scripted")
    replies: list[str] = []
    for word, path in SECRETS.items():
        replies += [_call("bash", {"command": f"cat {path}"}), _call("submit", {"answer": word})]
    script = iter(replies)
    provider.generate = lambda *_: [next(script)]
    return "tiny-scripted"


def _call(name: str, arguments: dict[str, str]) -> str:
    return f"<tool_call>\n{json.dumps({'name': name, 'arguments': arguments})}\n</tool_call>"


def main(args: Args) -> None:
    common = {"log_dir": str(logs_dir()), "tags": ["experiment:agent-sandbox"], "display": "none"}
    if args.scripted:
        runs = [eval(agent_sandbox(), model=f"loupe/{scripted()}", max_samples=1, **common)[0]]
    else:
        runs = [eval(agent_sandbox(), model=f"loupe/{args.model}", **common)[0]]
        if args.steer:
            model = get_model(f"loupe/{args.model}", interventions=json.loads(args.steer))
            runs.append(eval(agent_sandbox(), model=model, **common)[0])
    for log in runs:
        score = log.results.scores[0].metrics["accuracy"].value if log.results else None
        print(json.dumps({"run": f"e-{log.eval.eval_id}", "status": log.status, "accuracy": score}))


if __name__ == "__main__":
    main(tyro.cli(Args))
