"""Activation patching on the residual stream: which layer and position carry the difference."""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from loupe.analysis.views import heatmap
from loupe.models import blocks


def _token(lm: LanguageModel, text: str) -> int:
    ids = lm.tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        raise ValueError(f"{text!r} encodes to no tokens")
    return ids[0]


@torch.no_grad()
def patch_residual(
    lm: LanguageModel, clean: str, corrupt: str, answer: str, foil: str
) -> dict[str, Any]:
    """Patch the clean residual into the corrupt run at each (layer, position).

    The metric is the logit difference answer minus foil at the last position, normalised so 0 is
    the corrupt run and 1 is the clean run. Clean and corrupt must tokenize to the same length.
    """
    ids_clean = lm.tokenizer(clean)["input_ids"]
    ids_corrupt = lm.tokenizer(corrupt)["input_ids"]
    if len(ids_clean) != len(ids_corrupt):
        raise ValueError(
            f"clean and corrupt differ in length: {len(ids_clean)} vs {len(ids_corrupt)}"
        )
    a, b = _token(lm, answer), _token(lm, foil)
    layers = blocks(lm)

    clean_resid: list[torch.Tensor] = []
    with lm.trace(clean):
        for layer in layers:
            clean_resid.append(layer.output.save())
        clean_logits = lm.lm_head.output[0, -1].save()
    with lm.trace(corrupt):
        corrupt_logits = lm.lm_head.output[0, -1].save()

    def diff(logits: torch.Tensor) -> float:
        return float(logits[a] - logits[b])

    lo, hi = diff(corrupt_logits), diff(clean_logits)
    span = hi - lo if abs(hi - lo) > 1e-6 else 1.0
    n_pos = len(ids_clean)
    z: list[list[float]] = []
    for layer_i in range(len(layers)):
        row: list[float] = []
        for pos in range(n_pos):
            with lm.trace(corrupt):
                layers[layer_i].output[:, pos, :] = clean_resid[layer_i][:, pos, :]
                patched = lm.lm_head.output[0, -1].save()
            row.append((diff(patched) - lo) / span)
        z.append(row)
    tokens = [lm.tokenizer.decode(t) for t in ids_corrupt]
    return heatmap(
        f"Residual patching: {answer!r} vs {foil!r}",
        z,
        x=[f"{i}:{t}" for i, t in enumerate(tokens)],
        y=[str(i) for i in range(len(layers))],
        x_label="position",
        y_label="layer",
        note="1 = clean behaviour restored, 0 = corrupt behaviour",
    )
