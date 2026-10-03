"""The logit lens: what each layer's residual would predict if it were the last layer."""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.activations import positions, resid
from loupe.analysis.views import heatmap
from loupe.interventions import Plan
from loupe.models import final_norm


@torch.no_grad()
def logit_lens(
    lm: LanguageModel, prompt: str, plan: Plan | None = None, title: str | None = None
) -> tuple[torch.Tensor, dict[str, Any]]:
    """The top next token at every position, read from the embeddings and after every layer:
    token ids [1 + layers, positions], and a heatmap of their probabilities, each cell labelled
    with its token.
    """
    stream = resid(lm, prompt, plan)
    norm, head = final_norm(lm)._module, lm.lm_head._module
    param = next(head.parameters())
    ids: list[torch.Tensor] = []
    probs: list[torch.Tensor] = []
    for h in stream:
        p = head(norm(h.to(param))).float().softmax(-1)
        top = p.max(-1)
        ids.append(top.indices.cpu())
        probs.append(top.values.cpu())
    top_ids = torch.stack(ids)
    labels = [[str(lm.tokenizer.decode(int(t))) for t in row] for row in top_ids]
    view = heatmap(title or f"Logit lens: {prompt[-60:]!r}",
                   torch.stack(probs).round(decimals=4).tolist(), x=positions(lm, prompt),
                   y=["emb", *[str(i) for i in range(len(stream) - 1)]],
                   x_label="position", y_label="layer",
                   note="each cell: the layer's top next token and its probability",
                   labels=labels,
                   about="What the model would predict if it stopped at each layer (row), per "
                   "token (column). Watch where the final answer first appears.")  # fmt: skip
    return top_ids, view
