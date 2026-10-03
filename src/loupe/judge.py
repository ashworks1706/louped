"""Judge two eval runs pairwise with a local model, as an eval run of its own.

The judge run is filed under the baseline's experiment and names both runs in its metadata, so it
sits beside them and its samples show each pair with the judge's two replies.
"""

from __future__ import annotations

from inspect_ai import eval
from inspect_ai.model import Model

from loupe.core import logs_dir
from loupe.inspect_ext.judge import CRITERION, pairwise
from loupe.stores.evals import experiment_of, log_of


def judge(
    a: str,
    b: str,
    model: str | Model = "loupe/Qwen/Qwen2.5-1.5B-Instruct",
    criterion: str = CRITERION,
    limit: int | None = None,
    max_tokens: int = 512,
) -> str:
    """B's win rate over A, judged by model; returns the judge run's id."""
    found = {run: log_of(run) for run in (a, b)}
    if missing := [run for run, f in found.items() if f is None]:
        raise ValueError(f"not an eval run: {', '.join(missing)}")
    (path_a, log_a), (path_b, _) = found[a], found[b]  # type: ignore[misc]
    experiment = experiment_of(log_a)
    [log] = eval(pairwise(path_a, path_b, criterion), model=model, limit=limit,
                 max_tokens=max_tokens, log_dir=str(logs_dir()),
                 tags=[f"experiment:{experiment}"] if experiment else [],
                 metadata={"a": a, "b": b, "criterion": criterion},
                 display="none")  # fmt: skip
    if log.status != "success":
        raise RuntimeError(f"judging failed: {log.error.message if log.error else log.status}")
    return f"e-{log.eval.eval_id}"
