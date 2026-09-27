"""GSM8K test accuracy of the base and the GRPO model, scored by the same check as the reward.

    uv run --all-extras python experiments/gsm8k-grpo/eval.py --limit 500

Both go through the loupe/ provider, greedy; select the two runs under Runs and Compare them for
the paired difference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import tyro
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig
from inspect_ai.solver import generate

from loupe.core import home, logs_dir
from loupe.inspect_ext import as_scorer
from loupe.train.tasks import math_equal


@dataclass
class Args:
    base: str = "Qwen/Qwen2.5-0.5B-Instruct"
    tuned: str = "qwen2.5-0.5b-gsm8k-grpo"
    limit: int = 500
    max_tokens: int = 384


def task(limit: int, max_tokens: int) -> Task:
    lines = (home() / "data" / "gsm8k-grpo" / "test.jsonl").read_text().splitlines()[:limit]
    samples = []
    for i, line in enumerate(lines):
        row = json.loads(line)
        system, user = row["prompt"]
        samples.append(Sample(id=i, target=row["answer"], metadata={"answer": row["answer"]},
                              input=[ChatMessageSystem(content=system["content"]),
                                     ChatMessageUser(content=user["content"])]))  # fmt: skip
    return Task(dataset=samples, solver=generate(), scorer=as_scorer(math_equal),
                config=GenerateConfig(temperature=0, max_tokens=max_tokens))  # fmt: skip


def main(args: Args) -> None:
    for model in (args.base, args.tuned):
        eval(task(args.limit, args.max_tokens), model=f"loupe/{model}", log_dir=str(logs_dir()),
             tags=["experiment:gsm8k-grpo"], display="none")  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
