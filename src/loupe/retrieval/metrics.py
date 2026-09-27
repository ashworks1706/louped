"""Retrieval and answer metrics. Recall and nDCG score the retriever against gold passage ids;
exact match and F1 score the answer against gold answers after SQuAD normalisation."""

from __future__ import annotations

import math
import re
import string
from collections import Counter
from collections.abc import Sequence


def recall_at_k(retrieved: Sequence[str], gold: Sequence[str], k: int) -> float:
    """The share of gold passages among the first k retrieved."""
    return len(set(retrieved[:k]) & set(gold)) / len(set(gold)) if gold else 0.0


def ndcg_at_k(retrieved: Sequence[str], gold: Sequence[str], k: int) -> float:
    """Normalised discounted cumulative gain with binary relevance."""
    gain = sum(1 / math.log2(r + 2) for r, d in enumerate(retrieved[:k]) if d in set(gold))
    ideal = sum(1 / math.log2(r + 2) for r in range(min(len(set(gold)), k)))
    return gain / ideal if ideal else 0.0


def normalize(text: str) -> str:
    """Lower case, no punctuation, no articles, single spaces."""
    text = "".join(c for c in text.lower() if c not in string.punctuation)
    return " ".join(re.sub(r"\b(a|an|the)\b", " ", text).split())


def exact_match(prediction: str, answers: Sequence[str]) -> float:
    """1 when the normalised prediction equals any normalised answer."""
    return float(any(normalize(prediction) == normalize(a) for a in answers))


def f1(prediction: str, answers: Sequence[str]) -> float:
    """The best token-overlap F1 of the prediction against any answer."""
    pred = normalize(prediction).split()
    best = 0.0
    for answer in answers:
        gold = normalize(answer).split()
        common = sum((Counter(pred) & Counter(gold)).values())
        if common:
            p, r = common / len(pred), common / len(gold)
            best = max(best, 2 * p * r / (p + r))
    return best
