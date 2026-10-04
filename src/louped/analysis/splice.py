"""Spliced KV caches: passages encoded apart and joined, against the same text encoded whole.

A RAG runtime that caches each document's keys and values and splices them before the question
skips the documents' prefill, at two costs measured here. Encoded apart, documents no longer attend
to each other or to the prefix. Encoded from position 0 and placed later, their keys carry the
wrong rotary phase. rotated encodes each segment apart at its final positions, so only the lost
attention remains; at_zero adds the phase error. The score is the KL divergence of the next-token
distribution after the question from that of the whole text.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from nnsight import LanguageModel


@torch.no_grad()
def splice_divergence(
    lm: LanguageModel, passages: list[str], question: str, prefix: str = ""
) -> dict[str, float]:
    """KL(whole || spliced) at the question's last token, for the rotated and at_zero splices."""
    from transformers import DynamicCache

    model = lm._model
    device = next(model.parameters()).device

    def ids(text: str) -> torch.Tensor:
        return lm.tokenizer(text, add_special_tokens=False, return_tensors="pt")["input_ids"]

    segments = [s.to(device) for s in map(ids, [prefix, *passages]) if s.shape[1]]
    q = ids(question).to(device)
    whole = F.log_softmax(model(torch.cat([*segments, q], 1)).logits[0, -1].float(), -1)
    out: dict[str, float] = {}
    for variant in ("rotated", "at_zero"):
        caches, start = [], 0
        for s in segments:
            first = start if variant == "rotated" else 0
            pos = torch.arange(first, first + s.shape[1], device=device)[None]
            caches.append(model(s, position_ids=pos, use_cache=True).past_key_values)
            start += s.shape[1]
        cache = DynamicCache()
        for layer in range(len(caches[0].layers)):
            keys = torch.cat([c.layers[layer].keys for c in caches], 2)
            values = torch.cat([c.layers[layer].values for c in caches], 2)
            cache.update(keys, values, layer)
        pos = torch.arange(start, start + q.shape[1], device=device)[None]
        z = model(q, past_key_values=cache, position_ids=pos).logits[0, -1].float()
        out[variant] = float(
            F.kl_div(F.log_softmax(z, -1), whole, log_target=True, reduction="sum")
        )
    return out
