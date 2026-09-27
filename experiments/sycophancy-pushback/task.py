"""The pushback task on Sharma et al.'s are_you_sure TriviaQA questions, for Inspect and loupe grid.

inspect eval experiments/sycophancy-pushback/task.py@pushback --model loupe/Qwen/Qwen2.5-0.5B
"""

from __future__ import annotations

import json
import random
import urllib.request

from inspect_ai import Task, task

from loupe.core import home
from loupe.inspect_ext.tasks import pushback as pushback_task

SOURCE = (
    "https://raw.githubusercontent.com/meg-tong/sycophancy-eval/main/datasets/are_you_sure.jsonl"
)
Item = tuple[str, list[str], str]


def trivia(n: int, seed: int = 0) -> list[Item]:
    """n (question, answer aliases, wrong answer) triples, downloaded once under <home>/data."""
    cache = home() / "data" / "sycophancy" / "are_you_sure.jsonl"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(SOURCE, timeout=60) as r:
            cache.write_bytes(r.read())
    rows = [json.loads(line) for line in cache.read_text().splitlines()]
    out = [(r["base"]["question"], r["base"]["answer"], r["base"]["incorrect_answer"])
           for r in rows if r["base"]["dataset"] == "trivia_qa"]  # fmt: skip
    return random.Random(seed).sample(out, min(n, len(out)))


@task
def pushback(n: int = 100, seed: int = 0) -> Task:
    return pushback_task(trivia(n, seed))
