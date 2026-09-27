"""Attention patterns: where each head at each layer looks from every position."""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import positions
from loupe.analysis.views import heatmap
from loupe.models import attention, blocks


@torch.no_grad()
def attention_patterns(lm: LanguageModel, prompt: str) -> tuple[torch.Tensor, dict[str, Any]]:
    """Attention weights for one prompt: [layers, heads, query, key], and a heatmap per head.

    The SDPA and flash kernels never materialise the weights, so the model runs with eager
    attention for this trace and is switched back after; numerics match up to kernel rounding.
    """
    model: Any = lm._model
    previous = model.config._attn_implementation
    model.set_attn_implementation("eager")
    weights: list[torch.Tensor] = []
    try:
        with lm.trace(prompt):
            for layer in blocks(lm):
                weights.append(attention(layer).output[1][0].save())
    finally:
        model.set_attn_implementation(previous)
    pattern = torch.stack([w.float().cpu() for w in weights])
    slices = {
        f"layer {i} · head {j}": pattern[i, j].round(decimals=4).tolist()
        for i in range(pattern.shape[0])
        for j in range(pattern.shape[1])
    }
    labels = positions(lm, prompt)
    first = next(iter(slices.values()))
    view = heatmap(f"Attention: {prompt[-60:]!r}", first, x=labels, y=labels, x_label="key",
                   y_label="query", note="each row sums to 1", slices=slices)  # fmt: skip
    return pattern, view
