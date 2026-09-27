"""The check this experiment uses, as a GRPO reward (grpo.yaml) and an Inspect scorer (eval.py)."""

from __future__ import annotations

import re


def correct(completion: str, answer: str) -> float:
    """1 when the last number in the reply equals the reference answer."""
    numbers = re.findall(r"-?\d[\d,]*\.?\d*", completion)
    if not numbers:
        return 0.0
    last = numbers[-1].replace(",", "").rstrip(".")
    return float(last == answer.replace(",", ""))
