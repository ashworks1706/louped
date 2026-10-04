"""Directions read per token: how far each token's residual points along a direction, on one
prompt or over a dataset, where the top examples form a feature dashboard.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import torch
from nnsight import LanguageModel

from louped.analysis.activations import resid, token_strings
from louped.analysis.views import token_row, tokens
from louped.interventions import EMBED, Plan, apply_at
from louped.models import blocks

#: A per-token score of the residual: [..., hidden] -> [...].
Score = Callable[[torch.Tensor], torch.Tensor]


def along(direction: torch.Tensor) -> Score:
    """The residual's component along a direction, in residual units."""
    unit = direction.float() / direction.float().norm()
    return lambda h: h.float() @ unit.to(h.device)


@torch.no_grad()
def projection(
    lm: LanguageModel,
    prompt: str,
    reads: list[tuple[str, torch.Tensor, int]],
    plan: Plan | None = None,
) -> tuple[dict[str, torch.Tensor], dict[str, Any]]:
    """Each (name, direction, layer) read at every token of one prompt: {name: [positions]}, and
    the prompt's tokens coloured by each, one series per read. EMBED reads the embeddings.
    """
    stream = resid(lm, prompt, plan)
    out = {name: along(v)(stream[layer + 1]) for name, v, layer in reads}
    row = token_row(
        token_strings(lm, prompt), {k: v.round(decimals=4).tolist() for k, v in out.items()}
    )
    return out, tokens(f"Projections: {prompt[-60:]!r}", [row],
                       note="component of each token's residual along the direction",
                       about="How much of the direction each token carries. Darker tokens "
                       "express the concept more.")  # fmt: skip


@torch.no_grad()
def top_examples(
    lm: LanguageModel,
    prompts: list[str],
    layer: int,
    score: Score,
    title: str,
    k: int = 10,
    plan: Plan | None = None,
    batch_size: int = 16,
) -> tuple[torch.Tensor, dict[str, Any]]:
    """The k prompts where score peaks highest, highest first: each prompt's peak [prompts], and
    those k texts coloured per token. EMBED reads the embeddings.

    The peak skips the tokens every prompt starts and ends with (a chat template, a BOS token),
    which would otherwise rank the same template tokens first in every prompt.
    """
    ids = [lm.tokenizer(p)["input_ids"] for p in prompts]
    head, tail = shared_ends(ids)
    peaks: list[float] = []
    rows: list[tuple[float, dict[str, Any]]] = []
    for i in range(0, len(prompts), batch_size):
        chunk = prompts[i : i + batch_size]
        mask = lm.tokenizer(chunk, return_tensors="pt", padding=True)["attention_mask"].bool()
        with lm.trace(chunk):
            apply_at(lm, plan, EMBED)
            if layer == EMBED:
                h = blocks(lm)[0].input.save()
            else:
                for j in range(layer + 1):
                    apply_at(lm, plan, j)
                h = blocks(lm)[layer].output.save()
        scores = score(h).float().cpu()
        for text, m, v in zip(chunk, mask, scores, strict=True):
            real = v[m]
            peak = float(real[head : len(real) - tail].max())
            peaks.append(peak)
            series = {"activation": real.round(decimals=4).tolist()}
            rows.append((peak, token_row(token_strings(lm, text), series, f"peak {peak:.3f}")))
    rows.sort(key=lambda r: r[0], reverse=True)
    note = f"top {min(k, len(rows))} of {len(prompts)} texts by peak activation"
    if head or tail:
        note += f", skipping the {head} leading and {tail} trailing tokens all texts share"
    about = "The texts that point furthest along the direction. Darker tokens carry more of it."
    view = tokens(title, [r for _, r in rows[:k]], note, about=about)
    return torch.tensor(peaks), view


def shared_ends(ids: list[list[int]]) -> tuple[int, int]:
    """How many leading and trailing tokens every sequence shares, leaving each at least one."""
    shortest = min(len(x) for x in ids)
    if len(ids) < 2:
        return 0, 0
    head = 0
    while head < shortest - 1 and len({x[head] for x in ids}) == 1:
        head += 1
    tail = 0
    while head + tail < shortest - 1 and len({x[-1 - tail] for x in ids}) == 1:
        tail += 1
    return head, tail
