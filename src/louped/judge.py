"""Judge two eval runs pairwise with a local model, as an eval run of its own.

Which judge reads the pairs is a name: louped's default, or one of the project's judges/<name>.py
(louped.core.judges). The judge run is filed under the baseline's experiment and names both runs
and the judge in its metadata, so it sits beside them and its samples show each pair with the
judge's two replies.
"""

from __future__ import annotations

import hashlib

from inspect_ai import eval
from inspect_ai.model import Model

from louped.core import logs_dir
from louped.core.judges import judge_named, load_verdict, project_dir
from louped.inspect_ext.judge import pairwise, verdict
from louped.stores.evals import experiment_of, log_of


def judge(
    a: str,
    b: str,
    model: str | Model | None = None,
    criterion: str | None = None,
    limit: int | None = None,
    max_tokens: int = 512,
    name: str = "default",
) -> str:
    """B's win rate over A, judged by the judge called name (on model, else the judge's own; with
    criterion, else the judge's); returns the judge run's id."""
    spec = judge_named(name)
    found = {run: log_of(run) for run in (a, b)}
    if missing := [run for run, f in found.items() if f is None]:
        raise ValueError(f"not an eval run: {', '.join(missing)}")
    (path_a, log_a), (path_b, _) = found[a], found[b]  # type: ignore[misc]
    experiment = experiment_of(log_a)
    criterion = criterion or spec.criterion
    task = pairwise(path_a, path_b, criterion, spec.prompt, load_verdict(spec) or verdict)
    # which judge, as it stood: its file's path and hash, so the run says what code read it
    source = (project_dir() / spec.path).read_bytes() if spec.path else None
    meta = {"a": a, "b": b, "judge": spec.name, "criterion": criterion,
            "judge_path": spec.path,
            "judge_sha256": hashlib.sha256(source).hexdigest() if source else None}  # fmt: skip
    [log] = eval(task, model=model or spec.model, limit=limit, max_tokens=max_tokens,
                 log_dir=str(logs_dir()),
                 tags=[f"experiment:{experiment}"] if experiment else [],
                 metadata=meta, display="none")  # fmt: skip
    if log.status != "success":
        raise RuntimeError(f"judging failed: {log.error.message if log.error else log.status}")
    return f"e-{log.eval.eval_id}"
