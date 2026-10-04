"""How a model changes: measures re-run across training checkpoints, and two models compared layer
by layer on the same prompts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import torch
from nnsight import LanguageModel

from louped.analysis.activations import last_token_resid
from louped.analysis.views import line
from louped.models import load
from louped.vectors import diff_in_means

Measure = Callable[[LanguageModel], float]


def checkpoints(output_dir: Path) -> list[tuple[int, Path]]:
    """The adapters a training run kept (train.save_steps), by step."""
    found = [(int(m.group(1)), p) for p in output_dir.glob("checkpoint-*")
             if (m := re.fullmatch(r"checkpoint-(\d+)", p.name))]  # fmt: skip
    return sorted(found)


def over_checkpoints(
    base: str, steps: list[tuple[int, Path]], measures: dict[str, Measure]
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """Every measure on the base model (step 0) and on each checkpoint merged into it: {measure:
    [value per step]}, and a line of each against step. One model is loaded at a time.
    """
    points: list[tuple[int, Path | None]] = [(0, None), *steps]
    series: dict[str, list[float]] = {name: [] for name in measures}
    for _, adapter in points:
        lm = load(base, adapter=adapter)
        for name, measure in measures.items():
            series[name].append(float(measure(lm)))
        del lm
    view = line("Across training", [float(s) for s, _ in points], series, "step", "value",
                note="step 0 is the base model",
                about="Each measure on every saved checkpoint, to see when during training a "
                "behaviour appears.")  # fmt: skip
    return series, view


@torch.no_grad()
def model_diff(
    a: LanguageModel,
    b: LanguageModel,
    prompts: list[str],
    contrast: list[str] | None = None,
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """Two models of one architecture on the same prompts, per layer: the mean cosine between their
    last-token residuals, and the relative change in its norm. With contrast prompts, also the
    cosine between the two models' diff-in-means directions (prompts minus contrast), which says
    whether a feature the first model had survives in the second.
    """
    ra, rb = last_token_resid(a, prompts), last_token_resid(b, prompts)
    cos = torch.cosine_similarity(ra, rb, dim=-1).mean(-1)
    norm = (rb.norm(dim=-1).mean(-1) - ra.norm(dim=-1).mean(-1)) / ra.norm(dim=-1).mean(-1)
    series = {"residual cosine": cos.tolist(), "relative norm change": norm.tolist()}
    if contrast:
        ca, cb = last_token_resid(a, contrast), last_token_resid(b, contrast)
        da = torch.stack([diff_in_means(ra[i], ca[i]) for i in range(len(ra))])
        db = torch.stack([diff_in_means(rb[i], cb[i]) for i in range(len(rb))])
        series["direction cosine"] = torch.cosine_similarity(da, db, dim=-1).tolist()
    view = line("Model diff by layer", [float(i) for i in range(len(cos))], series, "layer",
                "value", note="last token, averaged over prompts",
                about="How much each layer changed between the two models. residual cosine "
                "near 1 means unchanged; direction cosine near 1, the feature survived.",
                )  # fmt: skip
    return series, view
