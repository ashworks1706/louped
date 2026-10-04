"""Steering sweeps: one Inspect task under Steer at every layer and strength, as one figure.

Each cell is an ordinary eval through the louped/ provider, logged where Inspect logs, so every
number opens its samples. Beside the score, the coherence cost: the mean KL divergence of the
next-token distribution on neutral prompts, base to steered, which rises when steering breaks the
model rather than moving the behaviour.
"""

from __future__ import annotations

import uuid
from typing import Any

import torch
from inspect_ai import Task, eval
from inspect_ai.model import get_model

from louped.analysis import heatmap, line, table
from louped.core import logs_dir
from louped.inspect_ext.provider import shared_model
from louped.interventions import Steer, compile, next_token_logprobs
from louped.models import chat
from louped.tracking import log_json, start_run

#: Prompts with no stake in any behaviour, for the coherence cost.
NEUTRAL = (
    "Describe the water cycle.",
    "Write a short poem about autumn.",
    "What is the capital of France?",
    "Explain how a bicycle works.",
    "List three uses of a paperclip.",
    "Summarise the plot of a fairy tale.",
    "How do plants make food?",
    "Give me a recipe for pancakes.",
)


def coherence_cost(
    model: str, spec: Steer, prompts: list[str], base: torch.Tensor | None = None
) -> float:
    """Mean KL(base || steered) of the next token after each prompt, in nats. base, the unsteered
    log-probabilities on these prompts, is computed when not given.
    """
    lm = shared_model(model)
    rendered = [chat(lm, p) for p in prompts]
    if base is None:
        base = next_token_logprobs(lm, rendered)
    steered = next_token_logprobs(lm, rendered, compile(lm, [spec]))
    return float((base.exp() * (base - steered)).sum(-1).mean())


def sweep(
    task: Task | str,
    model: str,
    vector: str,
    layers: list[int],
    alphas: list[float],
    metric: str,
    experiment: str = "steering-sweep",
    neutral: list[str] | None = None,
    seed: int = 0,
) -> str:
    """Run task at every (layer, alpha) and log the grid as an MLflow run; returns its UI id.

    metric names a result as the Run page shows it, scorer/metric (refusal/mean).
    """
    sweep_id = uuid.uuid4().hex[:8]
    prompts = list(neutral or NEUTRAL)
    score = [[0.0] * len(alphas) for _ in layers]
    cost = [[0.0] * len(alphas) for _ in layers]
    rows: list[list[Any]] = []
    links: list[list[str | None]] = []
    params = {"task": str(task), "model": model, "vector": vector, "layers": layers,
              "alphas": alphas, "metric": metric, "sweep": sweep_id}  # fmt: skip
    with start_run(experiment, name=f"sweep · {vector}", params=params, seed=seed) as run:
        lm = shared_model(model)
        base = next_token_logprobs(lm, [chat(lm, p) for p in prompts])
        for i, layer in enumerate(layers):
            for j, alpha in enumerate(alphas):
                spec = Steer(vector=vector, alpha=alpha, layer=layer)
                [log] = eval(
                    task,
                    model=get_model(f"louped/{model}", interventions=spec.model_dump()),
                    log_dir=str(logs_dir()),
                    tags=[f"experiment:{experiment}", f"sweep:{sweep_id}"],
                    metadata={"interventions": spec.model_dump()},
                    seed=seed,
                    display="none",
                )
                score[i][j] = _metric(log, metric)
                cost[i][j] = coherence_cost(model, spec, prompts, base)
                run_id = f"e-{log.eval.eval_id}"
                rows.append([layer, alpha, score[i][j], cost[i][j], run_id])
                links.append([None, None, None, None, f"/run/?id={run_id}"])
        x = [f"{a:g}" for a in alphas]
        y = [str(layer) for layer in layers]
        views = [
            heatmap(f"{metric} by layer and strength", score, x, y, "alpha", "layer",
                    about=f"{metric} with the vector added at one layer (row) and strength "
                    "(column). Look for where it moves most."),
            heatmap("Coherence cost: KL on neutral prompts (nats)", cost, x, y, "alpha", "layer",
                    about="How far steering pushes the model's next-token distribution on "
                    "unrelated prompts. Higher means the model is more broken; near 0 is free."),
            line(f"{metric} against strength", [float(a) for a in alphas],
                 {f"layer {layer}": score[i] for i, layer in enumerate(layers)}, "alpha", metric,
                 about=f"{metric} as strength grows, one line per layer."),
            table("Cells", ["layer", "alpha", metric, "KL", "eval run"], rows, links=links,
                  note="each eval run opens its samples",
                  about="Every layer and strength with its score and coherence cost."),
        ]  # fmt: skip
        for k, view in enumerate(views):
            log_json(view, f"views/{k:02d}-sweep.json")
    return f"m-{run.info.run_id}"


def _metric(log: Any, name: str) -> float:
    scorer, _, metric = name.partition("/")
    for score in log.results.scores if log.results else []:
        if score.name == scorer and metric in score.metrics:
            return float(score.metrics[metric].value)
    raise ValueError(f"no metric {name!r} in the eval results")
