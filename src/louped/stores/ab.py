"""Blind A/B: a person picks the better of two eval runs' answers, not told which run gave which.

The pairs are the samples both runs answered without error. Which answer sits left is decided per
sample by a seed drawn once for the two runs, so the page never says which is A and a reload shows
the same order. Picks are saved as a, b or tie in <home>/ab/<a>~<b>.json beside the seed, like a
judge run's labels. The result is B's win rate (B 1, tie 0.5, A 0) with the same 95% bootstrap
interval Compare uses, and each judge run of the same two runs against the person's picks.
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Literal

from louped.core import home
from louped.core.judges import POINTS
from louped.core.paths import inside
from louped.stores import evals
from louped.stores.compare import interval
from louped.stores.labels import kappa, pick
from louped.stores.runs import list_samples
from louped.stores.types import AbJudge, AbPair, AbResult, AbSession

Side = Literal["left", "right", "tie"]
RUN = re.compile(r"e-[A-Za-z0-9]+")
#: One pick saved at a time: a read-change-write of the file, from the server's threads.
_LOCK = threading.Lock()


def session(a: str, b: str) -> AbSession:
    """Every pair, each side placed by the seed, with the person's pick so far."""
    shared = _pairs(a, b)  # first: an unknown run leaves no file behind
    with _LOCK:  # two first reads draw one seed
        saved = _load(a, b)
    picks: dict[str, str] = saved["picks"]
    pairs: list[AbPair] = []
    for sample, (request, answer_a, answer_b) in shared.items():
        flipped = _flipped(saved["seed"], sample)
        left, right = (answer_b, answer_a) if flipped else (answer_a, answer_b)
        pairs.append(AbPair(sample=sample, request=request, left=left, right=right,
                            pick=_side(picks.get(sample), flipped)))  # fmt: skip
    return AbSession(a=a, b=b, pairs=pairs, labelled=sum(p.pick is not None for p in pairs))


def set_pick(a: str, b: str, sample: str, side: Side | None) -> AbSession:
    """Save the person's pick of one pair by the side they saw, or clear it with None."""
    if sample not in _pairs(a, b):
        raise ValueError(f"{a} and {b} share no answered sample {sample!r}")
    with _LOCK:
        saved = _load(a, b)
        if side is None:
            saved["picks"].pop(sample, None)
        else:
            flipped = _flipped(saved["seed"], sample)
            saved["picks"][sample] = {"tie": "tie", "left": "b" if flipped else "a",
                                      "right": "a" if flipped else "b"}[side]  # fmt: skip
        _write(_path(a, b), saved)
    return session(a, b)


def result(a: str, b: str) -> AbResult:
    """What the picks say: B's win rate with its interval, and each judge run's agreement."""
    shared = _pairs(a, b)
    path = _path(a, b)
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"picks": {}}
    picks = {k: v for k, v in saved["picks"].items() if k in shared}
    points = [POINTS[v] for v in picks.values()]
    low, high = interval(points) if len(points) > 1 else (None, None)
    judges: list[AbJudge] = []
    for run in evals.judge_runs(a, b):
        judged = {s.id: pick(v) for s in list_samples(run) or []
                  if (v := s.scores.get("b_wins")) is not None}  # fmt: skip
        both = [(judged[k], v) for k, v in picks.items() if k in judged]
        judges.append(AbJudge(run=run, labelled=len(both),
                              agreement=sum(x == y for x, y in both) / len(both) if both else None,
                              kappa=kappa(both) if both else None))  # fmt: skip
    return AbResult(a=a, b=b, labelled=len(picks), total=len(shared),
                    a_wins=sum(v == "a" for v in picks.values()),
                    b_wins=sum(v == "b" for v in picks.values()),
                    ties=sum(v == "tie" for v in picks.values()),
                    b_rate=sum(points) / len(points) if points else None, low=low, high=high,
                    judges=judges)  # fmt: skip


def _pairs(a: str, b: str) -> dict[str, tuple[str, str, str]]:
    """The samples both runs answered: the request and A's and B's answers."""
    return _read_pairs(_run(a), _run(b), evals.log_mtime(a), evals.log_mtime(b))


@lru_cache(maxsize=8)
def _read_pairs(a: str, b: str, _mtime_a: float | None, _mtime_b: float | None
                ) -> dict[str, tuple[str, str, str]]:  # fmt: skip
    """_pairs, read once per version of the two logs: every pick would read both whole."""
    left, right = evals.answers(a), evals.answers(b)
    if left is None or right is None:
        raise ValueError(f"not an eval run: {a if left is None else b}")
    return {k: (req, ans, right[k][1]) for k, (req, ans) in left.items() if k in right}


def _flipped(seed: int, sample: str) -> bool:
    """Whether B's answer sits left for this sample."""
    return random.Random(f"{seed}:{sample}").random() < 0.5


def _side(saved: str | None, flipped: bool) -> Side | None:
    if saved is None or saved == "tie":
        return saved  # type: ignore[return-value]
    return "left" if (saved == "b") == flipped else "right"


def _run(run_id: str) -> str:
    if not RUN.fullmatch(run_id):
        raise ValueError(f"not an eval run id: {run_id!r}")
    return run_id


def _path(a: str, b: str) -> Path:
    return inside(home() / "ab", f"{_run(a)}~{_run(b)}.json")


def _load(a: str, b: str) -> dict:
    """The saved seed and picks; for a new pair of runs a new seed, saved at once so the sides
    stay put between reads."""
    path = _path(a, b)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    saved = {"seed": random.SystemRandom().randrange(2**31), "picks": {}}
    _write(path, saved)
    return saved


def _write(path: Path, saved: dict) -> None:
    """Write whole or not at all: a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
