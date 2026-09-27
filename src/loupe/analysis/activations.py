"""Reading the residual stream."""

from __future__ import annotations

import torch
from nnsight import LanguageModel

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
