"""Attention kernels in plain torch, in the signature transformers' AttentionInterface calls.

Name one in a condition as attn="experiments/attention-kernels/kernels.py:sliding_window";
loupe.models.load registers it under the function's name with the eager mask, an additive float
[batch, 1, query, key] tensor. query is [batch, heads, query, dim], key and value
[batch, kv heads, key, dim]; each returns the output [batch, query, heads, dim] and its weights.
"""

from __future__ import annotations

from typing import Any

import torch

#: Keys each query sees in sliding_window, itself included.
WINDOW = 8
#: Keys each query keeps in top_k, by score.
TOP_K = 4


def _scores(module: Any, query: torch.Tensor, key: torch.Tensor, mask: torch.Tensor | None,
            scaling: float | None) -> torch.Tensor:  # fmt: skip
    """Masked scaled dot products [batch, heads, query, key], float32, keys repeated for GQA."""
    key = key.repeat_interleave(query.shape[1] // key.shape[1], dim=1)
    scores = (query.float() @ key.float().transpose(2, 3)) * (scaling or query.shape[-1] ** -0.5)
    return scores if mask is None else scores + mask[..., : key.shape[2]].float()


def _attend(scores: torch.Tensor, value: torch.Tensor, heads: int) -> tuple[torch.Tensor, Any]:
    weights = scores.softmax(-1)
    value = value.repeat_interleave(heads // value.shape[1], dim=1)
    out = (weights @ value.float()).to(value.dtype)
    return out.transpose(1, 2).contiguous(), weights.to(value.dtype)


def sliding_window(module: Any, query: torch.Tensor, key: torch.Tensor, value: torch.Tensor,
                   attention_mask: torch.Tensor | None, scaling: float | None = None,
                   **kwargs: Any) -> tuple[torch.Tensor, Any]:  # fmt: skip
    """Causal attention over the last WINDOW keys only."""
    scores = _scores(module, query, key, attention_mask, scaling)
    q, k = scores.shape[-2:]
    pos = torch.arange(k, device=scores.device)
    at = pos[k - q :, None]  # each query's own position among the keys
    scores = scores.masked_fill((pos[None, :] > at) | (pos[None, :] <= at - WINDOW), float("-inf"))
    return _attend(scores, value, query.shape[1])


def top_k(module: Any, query: torch.Tensor, key: torch.Tensor, value: torch.Tensor,
          attention_mask: torch.Tensor | None, scaling: float | None = None,
          **kwargs: Any) -> tuple[torch.Tensor, Any]:  # fmt: skip
    """Causal attention over the TOP_K highest-scoring keys of each query, the rest dropped."""
    scores = _scores(module, query, key, attention_mask, scaling)
    q, k = scores.shape[-2:]
    pos = torch.arange(k, device=scores.device)
    scores = scores.masked_fill(pos[None, :] > pos[k - q :, None], float("-inf"))
    kth = scores.topk(min(TOP_K, k), dim=-1).values[..., -1:]
    return _attend(scores.masked_fill(scores < kth, float("-inf")), value, query.shape[1])
