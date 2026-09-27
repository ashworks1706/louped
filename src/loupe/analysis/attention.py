"""Attention patterns: where each head at each layer looks from every position."""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import token_strings
from loupe.analysis.views import token_row, tokens
from loupe.interventions import EMBED, Plan, apply_at
from loupe.models import attention, blocks


@torch.no_grad()
def attention_patterns(
    lm: LanguageModel, prompt: str, plan: Plan | None = None
) -> tuple[torch.Tensor, dict[str, Any]]:
    """Attention weights for one prompt: [layers, heads, query, key], and a tokens view with one
    query-by-key grid per layer and head, which the UI draws as text coloured by what the query
    token attends to and as the grid itself.

    The SDPA and flash kernels never materialise the weights, so the model runs with eager
    attention for this trace and is switched back after; numerics match up to kernel rounding.
    """
    model: Any = lm._model
    previous = model.config._attn_implementation
    model.set_attn_implementation("eager")
    weights: list[torch.Tensor] = []
    try:
        with lm.trace(prompt):
            apply_at(lm, plan, EMBED)
            for i, layer in enumerate(blocks(lm)):
                weights.append(attention(layer).output[1][0].save())
                apply_at(lm, plan, i)
    finally:
        model.set_attn_implementation(previous)
    pattern = torch.stack([w.float().cpu() for w in weights])
    slices = {
        f"layer {i} · head {j}": pattern[i, j].round(decimals=4).tolist()
        for i in range(pattern.shape[0])
        for j in range(pattern.shape[1])
    }
    last = {name: rows[-1] for name, rows in slices.items()}
    note = "each query row sums to 1; hover or pick a token to see what it attends to"
    title = f"Attention: {prompt[-60:]!r}"
    return pattern, tokens(title, [token_row(token_strings(lm, prompt), last)], note, pairs=slices)
