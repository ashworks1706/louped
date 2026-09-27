"""Conditions by tasks by seeds: every domain's comparison, as one figure.

A condition is a set of loupe/ provider model args (interventions, adapters, phases, a diffusion
sampler) or another Inspect model (`{"model": "openai-api/zipy/qwen"}` for a product endpoint).
Each cell is ordinary Inspect evals, one per seed, logged where Inspect logs, so every number opens
its samples. Against the baseline condition each cell gets a paired bootstrap interval over the
samples both scored, so "beats the baseline beyond seed and sample variance" is read off the grid.

With `held`, a second score that must not move (correctness while a behaviour changes), each
condition gets a verdict: moved (the metric's interval excludes zero), held (the held score's
interval includes zero or is above it), or both.
"""

from __future__ import annotations

import uuid
from typing import Any

from inspect_ai import Task, eval
from inspect_ai.log import EvalLog
from inspect_ai.model import get_model

from loupe.analysis import heatmap, table
from loupe.core import logs_dir
from loupe.stores.compare import interval
from loupe.tracking import log_json, start_run

Scores = dict[tuple[str, int, int], float]


def grid(
    tasks: dict[str, Task | str],
    model: str,
    conditions: dict[str, dict[str, Any]],
    metric: str,
    seeds: list[int] | None = None,
    baseline: str | None = None,
    held: str | None = None,
    variants: dict[str, dict[str, Task | str]] | None = None,
    experiment: str = "grid",
) -> str:
    """Run every task under every condition and seed; log the grid as an MLflow run, returning its
    UI id. metric and held name results as the Run page shows them (scorer/metric). baseline is a
    condition name (default: the first). variants replaces a condition's task per column, such as
    the same task under a tuned prompt.
    """
    seeds = seeds or [0]
    names = list(conditions)
    base = baseline or names[0]
    if base not in conditions:
        raise ValueError(f"baseline {base!r} is not a condition")
    grid_id = uuid.uuid4().hex[:8]
    per: dict[tuple[str, str], tuple[Scores, Scores, list[str]]] = {}
    params = {"model": model, "tasks": list(tasks), "conditions": conditions, "metric": metric,
              "held": held, "seeds": seeds, "baseline": base, "grid": grid_id}  # fmt: skip
    with start_run(experiment, name=f"grid · {metric}", params=params) as run:
        for cond in names:
            for col, task in tasks.items():
                task = (variants or {}).get(cond, {}).get(col, task)
                per[cond, col] = _cell(task, model, conditions[cond], metric, held, seeds,
                                       [f"experiment:{experiment}", f"grid:{grid_id}"])  # fmt: skip
        for k, view in enumerate(_views(per, names, list(tasks), base, metric, held)):
            log_json(view, f"views/{k:02d}-grid.json")
    return f"m-{run.info.run_id}"


def _cell(
    task: Task | str,
    model: str,
    args: dict[str, Any],
    metric: str,
    held: str | None,
    seeds: list[int],
    tags: list[str],
) -> tuple[Scores, Scores, list[str]]:
    args = dict(args)
    target = (
        get_model(args.pop("model")) if "model" in args else get_model(f"loupe/{model}", **args)
    )
    scores: Scores = {}
    kept: Scores = {}
    runs: list[str] = []
    for seed in seeds:
        [log] = eval(task, model=target, log_dir=str(logs_dir()), tags=tags, seed=seed,
                     metadata={"condition": args}, display="none")  # fmt: skip
        runs.append(f"e-{log.eval.eval_id}")
        scores |= sample_scores(log, metric, seed)
        if held:
            kept |= sample_scores(log, held, seed)
    return scores, kept, runs


def sample_scores(log: EvalLog, name: str, seed: int = 0) -> Scores:
    """Each sample's value of a scorer, keyed by (sample id, epoch, seed), as floats (C is 1)."""
    from inspect_ai.scorer import value_to_float

    scorer = name.partition("/")[0]
    to_float = value_to_float()
    out: Scores = {}
    for s in log.samples or []:
        if s.scores and scorer in s.scores:
            out[str(s.id), s.epoch, seed] = to_float(s.scores[scorer].value)
    if not out:
        raise ValueError(f"no scorer {scorer!r} in the samples of {log.eval.task}")
    return out


def paired(a: Scores, b: Scores) -> tuple[float, float, float]:
    """Mean of b minus a over the samples both scored, with its 95% bootstrap interval."""
    diffs = [b[k] - a[k] for k in a if k in b]
    if not diffs:
        return 0.0, 0.0, 0.0
    low, high = interval(diffs)
    return sum(diffs) / len(diffs), low, high


def verdict(moved: tuple[float, float, float], kept: tuple[float, float, float] | None) -> str:
    """moved when the metric's interval excludes zero; held when the held score did not drop."""
    out = ["moved" if moved[1] > 0 or moved[2] < 0 else "same"]
    if kept is not None:
        out.append("held" if kept[2] >= 0 else "broke")
    return ", ".join(out)


def _views(
    per: dict[tuple[str, str], tuple[Scores, Scores, list[str]]],
    names: list[str],
    cols: list[str],
    base: str,
    metric: str,
    held: str | None,
) -> list[dict[str, Any]]:
    mean = [[_mean(per[c, t][0]) for t in cols] for c in names]
    deltas = [[paired(per[base, t][0], per[c, t][0]) for t in cols] for c in names]
    kept = [[paired(per[base, t][1], per[c, t][1]) if held else None for t in cols] for c in names]
    label = [[f"{m:.2f}" for m in row] for row in mean]
    dlabel = [[f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]" for d, lo, hi in row] for row in deltas]
    views = [
        heatmap(metric, mean, cols, names, "task", "condition", labels=label),
        heatmap(f"{metric} against {base}, 95% paired interval",
                [[d[0] for d in r] for r in deltas], cols, names, "task", "condition",
                labels=dlabel),
    ]  # fmt: skip
    if held:
        views.append(heatmap(f"{held} against {base}", [[k[0] if k else 0.0 for k in r]
                             for r in kept], cols, names, "task", "condition"))  # fmt: skip
    rows: list[list[Any]] = []
    links: list[list[str | None]] = []
    for i, c in enumerate(names):
        for j, t in enumerate(cols):
            d, lo, hi = deltas[i][j]
            runs = per[c, t][2]
            rows.append([c, t, round(mean[i][j], 4), f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]",
                         verdict(deltas[i][j], kept[i][j]) if c != base else "baseline",
                         runs[0]])  # fmt: skip
            links.append([None, None, None, None, None, f"/run/?id={runs[0]}"])
    head = ["condition", "task", metric, f"vs {base}", "verdict", "eval run"]
    note = "one eval run per seed; the first opens here"
    views.append(table("Cells", head, rows, links=links, note=note))
    return views


def _mean(scores: Scores) -> float:
    return sum(scores.values()) / len(scores) if scores else 0.0
