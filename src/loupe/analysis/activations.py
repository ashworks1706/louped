"""Reading the residual stream."""

from __future__ import annotations

import torch
from nnsight import LanguageModel

from loupe.interventions import EMBED, Plan, apply_at
from loupe.models import blocks


@torch.no_grad()
def last_token_resid(lm: LanguageModel, prompts: list[str], batch_size: int = 16) -> torch.Tensor:
    """The residual after every layer at each prompt's last token: [layers, prompts, hidden].

    Padding is on the left (loupe.models.load sets it), so the last position is every row's last
    real token. Stored as float32 on the CPU.
    """
    out: list[torch.Tensor] = []
    layers = blocks(lm)
    for i in range(0, len(prompts), batch_size):
        chunk = prompts[i : i + batch_size]
        saved: list[torch.Tensor] = []
        with lm.trace(chunk):
            for layer in layers:  # a loop, not a comprehension: nnsight traces this block's source
                saved.append(layer.output[:, -1, :].save())
        out.append(torch.stack([s.float().cpu() for s in saved]))
    return torch.cat(out, dim=1)


@torch.no_grad()
def resid(lm: LanguageModel, prompt: str, plan: Plan | None = None) -> torch.Tensor:
    """The residual stream of one prompt: [1 + layers, positions, hidden], the embeddings first,
    so the stream after layer L (or EMBED) is row L + 1.

    With a plan, each layer is read after its edits, so the result is the intervened stream.
    Float32 on the CPU.
    """
    saved: list[torch.Tensor] = []
    with lm.trace(prompt):
        apply_at(lm, plan, EMBED)
        saved.append(blocks(lm)[0].input[0].save())
        for i, layer in enumerate(blocks(lm)):
            apply_at(lm, plan, i)
            saved.append(layer.output[0].save())
    return torch.stack([s.float().cpu() for s in saved])


def token_strings(lm: LanguageModel, text: str) -> list[str]:
    """Each token of text, decoded on its own."""
    return [str(lm.tokenizer.decode(t)) for t in lm.tokenizer(text)["input_ids"]]


def positions(lm: LanguageModel, text: str) -> list[str]:
    """Each token of text as "index:token", the axis every per-position view is labelled with."""
    return [f"{i}:{t}" for i, t in enumerate(token_strings(lm, text))]
