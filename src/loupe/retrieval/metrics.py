"""Retrieval metrics: how many of a sample's gold passages the retriever returned. Answer exact
match and F1 are Inspect's own scorers."""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(retrieved: Sequence[str], gold: Sequence[str], k: int) -> float:
    """The share of gold passages among the first k retrieved."""
    return len(set(retrieved[:k]) & set(gold)) / len(set(gold)) if gold else 0.0
