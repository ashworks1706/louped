"""The logit lens: what each layer's residual would predict if it were the last layer."""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.views import table
from loupe.models import blocks


def _final_norm(lm: LanguageModel):
    for path in ("model.norm", "transformer.ln_f", "gpt_neox.final_layer_norm"):
        root = lm
        try:
            for part in path.split("."):
                root = getattr(root, part)
            return root
        except AttributeError:
            continue
    raise ValueError("no final norm found for this family")


@torch.no_grad()
def logit_lens(lm: LanguageModel, prompt: str, k: int = 5) -> dict[str, Any]:
    """A table: per layer, the top-k next tokens and their probabilities at the last position."""
    layers = blocks(lm)
    resid: list[torch.Tensor] = []
    with lm.trace(prompt):
        for layer in layers:
            resid.append(layer.output[:, -1, :].save())
    norm, head = _final_norm(lm)._module, lm.lm_head._module
    rows: list[list[Any]] = []
    for i, h in enumerate(resid):
        probs = head(norm(h)).float().softmax(-1)[0]
        top = probs.topk(k)
        tokens = [lm.tokenizer.decode(int(t)) for t in top.indices]
        rows.append(
            [i, *[f"{t!r} {p:.2f}" for t, p in zip(tokens, top.values.tolist(), strict=True)]]
        )
    columns = ["layer", *[f"top {j + 1}" for j in range(k)]]
    return table(f"Logit lens: {prompt[-60:]!r}", columns, rows)
