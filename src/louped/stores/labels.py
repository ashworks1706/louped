"""Human labels on a judge run's pairs, and how far the judge agrees with them.

A label is the person's pick for a pair: a, b or tie. Labels live in <home>/labels/<run>.json, one
small file per run, so they travel with louped's other state and a run's are deleted with a file.
The judge's pick for a pair is read from its b_wins score: 1 is b, 0 is a, anything between a tie.
Agreement is the share of labelled pairs where both picked the same, and Cohen's kappa, which
discounts what two raters with those base rates would agree on by chance.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Literal

from louped.core import home
from louped.stores.runs import list_samples
from louped.stores.types import Agreement

Label = Literal["a", "b", "tie"]
SCORE = "b_wins"


def _path(run_id: str):
    if not run_id.replace("-", "").isalnum():
        raise ValueError(f"not a run id: {run_id!r}")
    return home() / "labels" / f"{run_id}.json"


def get_labels(run_id: str) -> dict[str, Label]:
    """Every label on the run, by sample id."""
    path = _path(run_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def set_label(run_id: str, sample_id: str, label: Label | None) -> dict[str, Label]:
    """Label one sample of a judge run, or clear its label with None; returns every label."""
    if sample_id not in {s.id for s in _judged(run_id)}:
        raise ValueError(f"{run_id} has no judged sample {sample_id!r}")
    labels = get_labels(run_id)
    if label is None:
        labels.pop(sample_id, None)
    else:
        labels[sample_id] = label
    path = _path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(labels, indent=2, sort_keys=True), encoding="utf-8")
    return labels


def _judged(run_id: str):
    samples = list_samples(run_id)
    if not any(SCORE in s.scores for s in samples):
        raise ValueError(f"{run_id} is not a judge run: its samples have no {SCORE} score")
    return samples


def pick(b_wins: float) -> Label:
    return "b" if b_wins == 1 else "a" if b_wins == 0 else "tie"


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa of two raters' picks; None when chance agreement is total (one class)."""
    n = len(pairs)
    observed = sum(x == y for x, y in pairs) / n
    left, right = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    chance = sum(left[k] * right[k] for k in left) / n**2
    return None if chance == 1 else (observed - chance) / (1 - chance)


def agreement(run_id: str) -> Agreement:
    """How often the judge picked what the person picked, over the pairs they labelled."""
    judged = {s.id: v for s in _judged(run_id) if (v := s.scores.get(SCORE)) is not None}
    labels = get_labels(run_id)
    pairs = [(pick(v), labels[k]) for k, v in judged.items() if k in labels]
    if not pairs:
        return Agreement(labelled=0, total=len(judged), agreement=None, kappa=None)
    same = sum(x == y for x, y in pairs) / len(pairs)
    return Agreement(labelled=len(pairs), total=len(judged), agreement=same, kappa=kappa(pairs))
