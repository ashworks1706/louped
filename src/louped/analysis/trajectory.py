"""A masked diffusion model's denoising trajectory as a heatmap: which reply position each step
committed, with what confidence, and the reply as it stood after that step as the cell labels."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import torch

from louped.analysis.views import heatmap
from louped.models.diffusion import Diffusion, reply


def trajectory(
    d: Diffusion,
    prompt: str,
    title: str = "Denoising trajectory",
    on_step: Callable[[int, int], None] | None = None,
    **sampler: Any,
) -> dict[str, Any]:
    """Step by reply position: the confidence of each commit, labelled with the tokens committed
    so far (masked positions blank). sampler is denoise's arguments."""
    record: list[tuple[torch.Tensor, torch.Tensor]] = []
    text = reply(d, prompt, on_step, record, **sampler)
    length = record[0][0].shape[1]
    labels = []
    for x, _ in record:
        ids_now = x[0].tolist()
        toks = d.tokenizer.convert_ids_to_tokens(ids_now)
        labels.append(["" if i == d.mask_id else t for i, t in zip(ids_now, toks, strict=True)])
    return heatmap(title, [c[0].tolist() for _, c in record], [str(i) for i in range(length)],
                   [str(s) for s in range(len(record))], "reply position", "step",
                   note=f"reply: {text}", labels=labels,
                   about="A diffusion model fills in its reply over steps (rows). Each cell is "
                   "the token at that position once unmasked, shaded by its confidence.",
                   )  # fmt: skip
