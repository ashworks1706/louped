"""Verifiable tasks for GRPO and evals, from prebuilt generators and checkers. Needs the rl extra.

reasoning-gym generates tasks procedurally, offline and at any size, each with its own scorer;
`gym_rows` turns one into GRPO rows and `gym` is the matching check. `math_equal` compares a
maths answer symbolically with math-verify. All three are plain checks: a GRPO reward in the YAML
(loupe.train.tasks:gym) and an Inspect scorer through as_scorer.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

#: Asks for the final answer in the tag gym reads it from.
GYM_INSTRUCTION = (
    "Think step by step, then give only the final answer inside <answer></answer> tags."
)


def gym_rows(task: str, size: int, seed: int = 0) -> list[dict[str, Any]]:
    """GRPO rows for a reasoning-gym task: the question as the prompt, the entry for the check."""
    import reasoning_gym

    out = []
    for entry in reasoning_gym.create_dataset(task, size=size, seed=seed):
        prompt = [{"role": "system", "content": GYM_INSTRUCTION},
                  {"role": "user", "content": entry["question"]}]  # fmt: skip
        out.append({"prompt": prompt, "task": task, "answer": str(entry["answer"]),
                    "entry": json.dumps(entry)})  # fmt: skip
    return out


def gym(completion: str, task: str, entry: str) -> float:
    """The task's own score for the reply's <answer> tag; 0 without one."""
    from reasoning_gym import get_score_answer_fn
    from reasoning_gym.utils import extract_answer

    answer = extract_answer(completion)
    if answer is None:
        return 0.0
    score = cast(Callable[..., float], get_score_answer_fn(task))  # typed as taking nothing
    return float(score(answer, json.loads(entry)))


def math_equal(completion: str, answer: str) -> float:
    """1 when the reply's final answer equals the reference, symbolically (1/2 equals 0.5)."""
    from math_verify import parse, verify

    got = parse(completion)
    return float(bool(got) and verify(parse(answer), got))
