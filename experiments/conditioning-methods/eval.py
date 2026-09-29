"""The held-out capitals under the base model, a system-prompt line and the LoRA, as one grid:
words per answer (should fall) and whether the answer names the capital (should hold).

    uv run --all-extras python experiments/conditioning-methods/eval.py   (after data.py and sft)

ReFT runs in pyreft's own environment, so its test replies and the same two scores are on its
training run (test/reft_words, test/reft_contains_target), next to the base model's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import tyro
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate, system_message

from loupe.core import home
from loupe.grid import grid
from loupe.inspect_ext.scorers import as_scorer
from loupe.inspect_ext.tasks import says

LINE = "Answer with the name only, in one word where you can."


def correct(completion: str, target: str) -> float:
    """Names the capital."""
    return float(says(completion, target))


def words(completion: str) -> float:
    """Length of the answer in words."""
    return float(len(completion.split()))


def capitals(line: str | None = None, name: str = "base") -> Task:
    path = home() / "data" / "conditioning-methods" / "test.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    data = [Sample(id=r["id"], input=r["messages"][-1]["content"], target=r["reply"]) for r in rows]
    solver = ([system_message(line)] if line else []) + [generate(max_tokens=64)]
    return Task(dataset=data, solver=solver, scorer=[as_scorer(words), as_scorer(correct)],
                name=f"capitals-{name}")  # fmt: skip


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    lora: str = "conditioning-methods-lora"
    """The merged LoRA, as sft.yaml saves it."""


def main(args: Args) -> None:
    conds = {"base": {}, "prompt": {}, "lora": {"model": f"loupe/{args.lora}"}}
    variants: dict[str, dict[str, Task | str]] = {"prompt": {"capitals": capitals(LINE, "prompt")}}
    print(grid({"capitals": capitals()}, args.model, conds, "words/mean", held="correct/mean",
               variants=variants, experiment="conditioning-methods"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
