"""Attention patterns: where each head at each layer looks from every position, and how much of the
last position's attention lands on a span, such as a retrieved passage."""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import token_strings
from loupe.analysis.views import by_head, token_row, tokens
from loupe.interventions import EMBED, Plan, apply_at, apply_heads
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
    pattern = _weights(lm, prompt, plan)
    slices = {
        f"layer {i} · head {j}": pattern[i, j].round(decimals=4).tolist()
        for i in range(pattern.shape[0])
        for j in range(pattern.shape[1])
    }
    last = {name: rows[-1] for name, rows in slices.items()}
    note = "each query row sums to 1; hover or pick a token to see what it attends to"
    title = f"Attention: {prompt[-60:]!r}"
    return pattern, tokens(title, [token_row(token_strings(lm, prompt), last)], note, pairs=slices)


@torch.no_grad()
def attention_to_span(
    lm: LanguageModel, prompt: str, span: str, plan: Plan | None = None
) -> tuple[torch.Tensor, dict[str, Any]]:
    """The share of the last position's attention on the tokens of span, the last place it occurs
    in prompt: [layers, heads], and a heatmap of it by layer and head.

    Put a generated reply after the prompt to read the mass from its last token.
    """
    start = prompt.rfind(span)
    if not span or start < 0:
        raise ValueError(f"{span[:40]!r} does not occur in the prompt")
    end = start + len(span)
    offsets = lm.tokenizer(prompt, return_offsets_mapping=True)["offset_mapping"]
    keys = [i for i, (a, b) in enumerate(offsets) if a < end and b > start and b > a]
    mass = _weights(lm, prompt, plan)[:, :, -1, keys].sum(-1)
    view = by_head(
        f"Attention on {span[:40]!r} from the last position",
        mass.round(decimals=4).tolist(),
        f"share of attention on {len(keys)} span tokens; each row of weights sums to 1",
    )
    return mass, view


def _weights(lm: LanguageModel, prompt: str, plan: Plan | None) -> torch.Tensor:
    """Eager attention weights [layers, heads, query, key], float32 on CPU."""
    model: Any = lm._model
    previous = model.config._attn_implementation
    model.set_attn_implementation("eager")
    weights: list[torch.Tensor] = []
    try:
        with lm.trace(prompt):
            apply_at(lm, plan, EMBED)
            for i, layer in enumerate(blocks(lm)):
                apply_heads(lm, plan, i)
                weights.append(attention(layer).output[1][0].save())
                apply_at(lm, plan, i, heads=False)
    finally:
        model.set_attn_implementation(previous)
    return torch.stack([w.float().cpu() for w in weights])
