"""Two eval runs compared sample by sample: for each score, the paired difference and how sure.

Runs over the same samples are paired, so the difference of means is judged against the spread of
per-sample differences, not of scores: a paired bootstrap, seeded, so the interval is reproducible.
"""

from __future__ import annotations

import random
from functools import lru_cache

from louped.stores import evals
from louped.stores.runs import list_samples
from louped.stores.types import Comparison, PairedScore

RESAMPLES = 2000


def interval(diffs: list[float], seed: int = 0) -> tuple[float, float]:
    """The 95% percentile bootstrap interval of the mean difference."""
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(RESAMPLES))
    return means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def compare(a: str, b: str) -> Comparison:
    """Every score both runs have, over the samples (id and epoch) both scored."""
    return _compare(a, b, evals.log_mtime(a), evals.log_mtime(b))


@lru_cache(maxsize=64)
def _compare(a: str, b: str, _mtime_a: float | None, _mtime_b: float | None) -> Comparison:
    left = {(s.id, s.epoch): s.scores for s in list_samples(a)}
    right = {(s.id, s.epoch): s.scores for s in list_samples(b)}
    shared = [k for k in left if k in right]
    names = sorted({n for k in shared for n in left[k]} & {n for k in shared for n in right[k]})
    scores: list[PairedScore] = []
    for name in names:
        pairs = [
            (x, y)
            for k in shared
            if (x := left[k].get(name)) is not None and (y := right[k].get(name)) is not None
        ]
        if not pairs:
            continue
        diffs = [y - x for x, y in pairs]
        low, high = interval(diffs)
        n = len(pairs)
        scores.append(
            PairedScore(
                name=name,
                n=n,
                mean_a=sum(x for x, _ in pairs) / n,
                mean_b=sum(y for _, y in pairs) / n,
                diff=sum(diffs) / n,
                low=low,
                high=high,
                up=sum(d > 0 for d in diffs),
                down=sum(d < 0 for d in diffs),
            )
        )
    return Comparison(a=a, b=b, only_a=len(left) - len(shared), only_b=len(right) - len(shared),
                      scores=scores)  # fmt: skip
