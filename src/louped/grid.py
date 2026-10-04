"""Conditions by tasks by seeds: every domain's comparison, as one figure.

A condition is a set of louped/ provider model args (interventions, adapters, phases, a diffusion
sampler), optionally with another Inspect model: `endpoint(...)` for any OpenAI-compatible server
(vLLM, llama.cpp, Ollama, your own system's API), `{"model": "louped/other", ...}` for another local
model on the same tasks. An api_key in a condition reaches the model and never a log.
Each cell is ordinary Inspect evals, one per seed, logged where Inspect logs, so every number opens
its samples. Against the baseline condition each cell gets a paired bootstrap interval over the
samples both scored, so "beats the baseline beyond seed and sample variance" is read off the grid.

With `held`, a second score that must not move (correctness while a behaviour changes), each
condition gets a verdict: moved (the metric's interval excludes zero), held (the held score's
interval includes zero or is above it), or both. Each of `extra`, such as latency/mean
(louped.inspect_ext.inference), is read from the same runs and drawn as its own figure, and as a
scatter of the metric against it, so a change's cost is read beside what it buys.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from inspect_ai import Task, eval
from inspect_ai.log import EvalLog
from inspect_ai.model import Model, get_model

from louped.analysis import heatmap, scatter, table
from louped.core import logs_dir
from louped.stores.compare import interval
from louped.tracking import log_json, start_run

Scores = dict[tuple[str, int, int], float]
#: A cell's metric and held scores, its eval runs, and its extra scores by name.
Cell = tuple[Scores, Scores, list[str], dict[str, Scores]]


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
    extra: list[str] | None = None,
) -> str:
    """Run every task under every condition and seed; log the grid as an MLflow run, returning its
    UI id. metric and held name results as the Run page shows them (scorer/metric). baseline is a
    condition name (default: the first). variants replaces a condition's task per column, such as
    the same task under a tuned prompt. extra names more results to draw, mean and difference
    against the baseline, without a verdict.
    """
    seeds = seeds or [0]
    names = list(conditions)
    base = baseline or names[0]
    if base not in conditions:
        raise ValueError(f"baseline {base!r} is not a condition")
    grid_id = uuid.uuid4().hex[:8]
    per: dict[tuple[str, str], Cell] = {}
    # Condition args go in conditions.json; the params hold their names.
    params = {"model": model, "tasks": list(tasks), "conditions": names, "metric": metric,
              "held": held, "seeds": seeds, "baseline": base, "grid": grid_id,
              "extra": extra or []}  # fmt: skip
    # Every condition's model loads before any eval runs.
    targets = {c: _target(model, conditions[c]) for c in names}
    with start_run(experiment, name=f"grid · {metric}", params=params) as run:
        log_json(_plain(conditions), "conditions.json")
        for cond in names:
            for col, task in tasks.items():
                task = (variants or {}).get(cond, {}).get(col, task)
                per[cond, col] = _cell(task, cond, targets[cond], conditions[cond], metric, held,
                                       seeds, [f"experiment:{experiment}", f"grid:{grid_id}"],
                                       extra or [])  # fmt: skip
        views = _views(per, names, list(tasks), base, metric, held)
        for name in extra or []:
            views[-1:-1] = [_extra(name, per, names, list(tasks), base),
                            _tradeoff(name, per, names, list(tasks), metric)]  # fmt: skip
        for k, view in enumerate(views):
            log_json(view, f"views/{k:02d}-grid.json")
    return f"m-{run.info.run_id}"


def _target(model: str, args: dict[str, Any]) -> Model:
    args = {k: v for k, v in args.items() if k != "roles"}
    return get_model(args.pop("model", f"louped/{model}"), **args)


def _roles(args: dict[str, Any]) -> dict[str, Model] | None:
    """A condition's other model roles, such as the user a benchmark simulates: role to an
    Inspect model name, or to that model's args as a condition gives them."""
    roles = args.get("roles") or {}
    return {role: _target("", spec if isinstance(spec, dict) else {"model": spec})
            for role, spec in roles.items()} or None  # fmt: skip


def _cell(
    task: Task | str,
    cond: str,
    target: Model,
    args: dict[str, Any],
    metric: str,
    held: str | None,
    seeds: list[int],
    tags: list[str],
    extra: list[str],
) -> Cell:
    scores: Scores = {}
    kept: Scores = {}
    runs: list[str] = []
    more: dict[str, Scores] = {name: {} for name in extra}
    for seed in seeds:
        [log] = eval(task, model=target, model_roles=_roles(args), log_dir=str(logs_dir()),
                     tags=tags, seed=seed,
                     metadata={"condition": _plain(args), "cell": f"{cond} · seed {seed}"},
                     display="none")  # fmt: skip
        if log.status != "success":
            reason = log.error.message if log.error else log.status
            raise RuntimeError(f"{log.eval.task} failed under {_plain(args)}: {reason}")
        runs.append(f"e-{log.eval.eval_id}")
        scores |= sample_scores(log, metric, seed)
        if held:
            kept |= sample_scores(log, held, seed)
        for name in extra:
            more[name] |= sample_scores(log, name, seed)
    return scores, kept, runs, more


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
    """Mean of b minus a over the samples both scored, with its 95% bootstrap interval. Seeds of
    one sample are averaged first, so the interval resamples samples, not seeds."""
    per: dict[tuple[str, int], list[float]] = {}
    for k in a:
        if k in b:
            per.setdefault(k[:2], []).append(b[k] - a[k])
    diffs = [sum(d) / len(d) for d in per.values()]
    if not diffs:
        raise ValueError("no sample was scored under both conditions; a variant task must keep "
                         "the baseline's sample ids to be paired with it")  # fmt: skip
    low, high = interval(diffs)
    return sum(diffs) / len(diffs), low, high


def verdict(moved: tuple[float, float, float], kept: tuple[float, float, float] | None) -> str:
    """moved when the metric's interval excludes zero; held when the held score did not drop."""
    out = ["moved" if moved[1] > 0 or moved[2] < 0 else "same"]
    if kept is not None:
        out.append("held" if kept[2] >= 0 else "broke")
    return ", ".join(out)


def _views(
    per: dict[tuple[str, str], Cell],
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
    dlabel = [[f"{d:+.2f}{'*' if lo > 0 or hi < 0 else ''}" for d, lo, hi in row] for row in deltas]
    views = [
        heatmap(metric, mean, cols, names, "task", "condition", labels=label,
                about=f"Each cell is {metric} for one condition (row) on one task (column), "
                "averaged over samples and seeds."),
        heatmap(f"{metric} against {base}, 95% paired interval",
                [[d[0] for d in r] for r in deltas], cols, names, "task", "condition",
                labels=dlabel, note="* the interval excludes zero; intervals in Cells",
                about=f"Each cell is the condition's {metric} minus {base}'s, on the same "
                "samples. Green is higher, red lower. * means the 95% bootstrap interval "
                f"excludes zero: a real difference, not noise. {base}'s own row is zero."),
    ]  # fmt: skip
    if held:
        views.append(heatmap(f"{held} against {base}", [[k[0] if k else 0.0 for k in r]
                             for r in kept], cols, names, "task", "condition",
                             about=f"What the change should not break: {held} minus "
                             f"{base}'s, on the same samples. Red means it dropped."))  # fmt: skip
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
    about = (
        f"One row per condition and task. vs {base} is the paired difference with its 95% "
        "interval. verdict: moved when the interval excludes zero, same when it does not; "
        "held or broke says whether the held score dropped."
    )
    views.append(table("Cells", head, rows, links=links, note=note, about=about))
    return views


def _extra(
    name: str, per: dict[tuple[str, str], Cell], names: list[str], cols: list[str], base: str
) -> dict[str, Any]:
    mean = [[_mean(per[c, t][3][name]) for t in cols] for c in names]
    delta = [[paired(per[base, t][3][name], per[c, t][3][name])[0] for t in cols] for c in names]
    labels = [[f"{m:.3g} ({d:+.3g})" for m, d in zip(r, e, strict=True)]
              for r, e in zip(mean, delta, strict=True)]  # fmt: skip
    return heatmap(name, mean, cols, names, "task", "condition", labels=labels,
                   note=f"mean (difference against {base})",
                   about=f"{name} per condition and task: the mean, and in brackets its "
                   f"difference from {base}.")  # fmt: skip


def _tradeoff(
    name: str, per: dict[tuple[str, str], Cell], names: list[str], cols: list[str], metric: str
) -> dict[str, Any]:
    """metric against an extra, one point per condition and task: what a change costs for what it
    buys."""
    points = [(c if len(cols) == 1 else f"{c} · {t}", _mean(per[c, t][3][name]),
               _mean(per[c, t][0])) for c in names for t in cols]  # fmt: skip
    return scatter(f"{metric} against {name}", points, name, metric,
                   note="means over seeds and samples",
                   about=f"One point per condition: {metric} against {name}. Compare what a "
                   "change buys (up) with what it costs (along).")  # fmt: skip


def endpoint(
    model: str, base_url: str | None = None, api_key: str | None = None, agent: bool = False
) -> dict[str, Any]:
    """A condition that runs model: any Inspect model (louped/<hub id> runs locally), or with
    base_url, a model an OpenAI-compatible server serves under that id, e.g.
    endpoint("qwen2.5:7b-instruct", "http://localhost:11434/v1") for Ollama. With agent, the
    server is an agent that runs its own tools and reports them (louped.inspect_ext.agent)."""
    if base_url is None:
        return {"model": model}
    prefix = "agent/" if agent else "openai-api/endpoint/"
    name = model if model.startswith(("openai-api/", "agent/")) else prefix + model
    return {"model": name, "base_url": base_url, "api_key": api_key or "local"}


def _plain(value: Any) -> Any:
    """JSON data, with any other value (a function) as its repr, and no api_key."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if k != "api_key"}
    return json.loads(json.dumps(value, default=repr))


def _mean(scores: Scores) -> float:
    return sum(scores.values()) / len(scores) if scores else 0.0
