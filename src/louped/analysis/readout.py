"""One prompt read layer by layer, for Probe's Inspect: what each layer would predict (the logit
lens, with its top tokens, entropy and distance from the final answer), where one target token's
probability and rank rise, which layer's attention and MLP and which head write that token (direct
logit attribution), and what each head does (entropy, previous-token and first-token attention).

Direct logit attribution freezes the final norm at the last layer's scale, so each part's
contribution is linear: the parts add up to the target's logit, less the norm's and head's biases.
"""

from __future__ import annotations

from typing import Any

import torch
from nnsight import LanguageModel

from louped.analysis.activations import token_strings
from louped.interventions import EMBED, Plan, apply_at, apply_heads
from louped.models import attention, blocks, final_norm, n_heads, out_proj

#: Top tokens kept for each layer and position.
TOP = 5
#: Per-head attribution is layers x heads x positions; above this, only the last position's.
MAX_HEAD_CELLS = 200_000


def _r(t: torch.Tensor, digits: int = 4) -> Any:
    return t.round(decimals=digits).tolist()


def _frozen_norm(norm: torch.nn.Module, final: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """The final norm as a linear map at the last layer's scale: its per-position scale and its
    gain, and whether it centres (LayerNorm) folded into how the direction is read."""
    name = type(norm).__name__
    weight = getattr(norm, "weight", None)
    gain = torch.ones(final.shape[-1]) if weight is None else weight.detach().float().cpu()
    if "Gemma" in name:  # Gemma's RMSNorm scales by 1 + weight
        gain = 1 + gain
    eps = float(getattr(norm, "eps", None) or getattr(norm, "variance_epsilon", 1e-6))
    centred = final - final.mean(-1, keepdim=True) if "RMS" not in name else final
    scale = (centred.pow(2).mean(-1) + eps).sqrt()
    return scale, gain


@torch.no_grad()
def readout(
    lm: LanguageModel,
    prompt: str,
    plan: Plan | None = None,
    target: str | None = None,
    pattern: torch.Tensor | None = None,
) -> dict[str, Any]:
    """The prompt read at every layer and position, in the fields of
    louped.server.playground.Readout, which says what each holds. target: the token to follow
    (its first token), by default the model's prediction at the last position. pattern: attention
    weights [layers, heads, query, key] (louped.analysis.attention_patterns), for the heads'
    scores."""
    layers = blocks(lm)
    heads = n_heads(lm)
    saved_in: list[Any] = []
    saved_attn: list[Any] = []
    saved_out: list[Any] = []
    with lm.trace(prompt):
        apply_at(lm, plan, EMBED)
        emb = layers[0].input[0].save()
        for i, layer in enumerate(layers):
            apply_heads(lm, plan, i)
            attn = attention(layer)
            saved_in.append(out_proj(attn).input.save())
            saved_attn.append(attn.output[0].save())
            apply_at(lm, plan, i)
            saved_out.append(layer.output[0].save())
    # each block's output is the residual [positions, hidden], as in louped.analysis.resid
    stream = torch.stack([emb.float().cpu(), *(o.float().cpu() for o in saved_out)])
    norm, head = final_norm(lm)._module, lm.lm_head._module
    param = next(head.parameters())
    logits = torch.stack([head(norm(h.to(param))).float().cpu() for h in stream])  # [L+1, T, V]
    logp = logits.log_softmax(-1)
    probs = logp.exp()
    final = logp[-1]

    if target:
        ids = lm.tokenizer(target, add_special_tokens=False)["input_ids"]
        if not ids:
            raise ValueError(f"{target!r} has no tokens")
        tid = int(ids[0])
    else:
        tid = int(final[-1].argmax())

    top = probs.topk(TOP, dim=-1)
    tp = probs[..., tid]
    rank = (probs > tp.unsqueeze(-1)).sum(-1)
    entropy = -(probs * logp).sum(-1)
    kl = (final.exp() * (final - logp)).sum(-1)

    # direct logit attribution through the frozen final norm
    scale, gain = _frozen_norm(norm, stream[-1])
    weights: torch.Tensor = head.weight.detach().float().cpu()
    direction = weights[tid] * gain
    if "RMS" not in type(norm).__name__:
        direction = direction - direction.mean()

    def dla(x: torch.Tensor) -> torch.Tensor:
        return (x @ direction) / scale

    attn_out = torch.stack([a.float().cpu().reshape(stream.shape[1:]) for a in saved_attn])
    mlp_out = stream[1:] - stream[:-1] - attn_out
    t = stream.shape[1]
    positions = list(range(t)) if len(layers) * heads * t <= MAX_HEAD_CELLS else [t - 1]
    per_head: list[Any] = []
    for i in range(len(layers)):
        proj = out_proj(attention(layers[i]))._module
        w_o = proj.weight.detach().float().cpu()
        if type(proj).__name__ == "Conv1D":  # GPT-2 keeps its projection as [in, out]
            w_o = w_o.T
        read = (w_o.T @ direction).reshape(heads, -1)  # [heads, head_dim]
        x = saved_in[i].float().cpu().reshape(t, heads, -1)[positions]  # [P, heads, head_dim]
        per_head.append(_r(((x * read).sum(-1) / scale[positions, None]).T))

    if pattern is not None:
        p = pattern.float()
        q = p.shape[-1]
        head_entropy = -(p * (p + 1e-12).log()).sum(-1).mean(-1)
        if q > 1:
            idx = torch.arange(1, q)
            head_prev = p[:, :, idx, idx - 1].mean(-1)
            head_first = p[:, :, 1:, 0].mean(-1)
        else:
            head_prev = head_first = torch.zeros(p.shape[:2])
    else:
        head_entropy = head_prev = head_first = torch.zeros(len(layers), heads)

    named = {int(i) for i in top.indices.flatten().tolist()} | {tid}
    return dict(
        tokens=token_strings(lm, prompt),
        layers=["emb", *(str(i) for i in range(len(layers)))],
        vocab={i: str(lm.tokenizer.decode([i])) for i in sorted(named)},
        top_ids=top.indices.tolist(),
        top_probs=_r(top.values),
        entropy=_r(entropy, 3),
        kl=_r(kl.clamp(min=0), 3),
        target=tid,
        target_prob=_r(tp, 5),
        target_rank=rank.tolist(),
        target_logit=_r(logits[-1, :, tid], 3),
        dla_embed=_r(dla(stream[0]), 3),
        dla_attn=_r(torch.stack([dla(a) for a in attn_out]), 3),
        dla_mlp=_r(torch.stack([dla(m) for m in mlp_out]), 3),
        dla_heads=per_head,
        head_positions=positions,
        head_entropy=_r(head_entropy, 3),
        head_prev=_r(head_prev, 3),
        head_first=_r(head_first, 3),
    )
