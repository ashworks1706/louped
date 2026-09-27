"""Greedy generation and next-token logits with a plan applied, batched.

The two calls every intervention experiment needs, and the ones the Inspect provider and the
Playground are built on.
"""

from __future__ import annotations

import torch
from nnsight import LanguageModel

from loupe.interventions.specs import Plan, apply


@torch.no_grad()
def generate(
    lm: LanguageModel,
    prompts: list[str],
    plan: Plan | None = None,
    max_new_tokens: int = 64,
    batch_size: int = 8,
) -> list[str]:
    """Greedy completions, with the plan applied at every generated token when one is given."""
    out: list[str] = []
    for i in range(0, len(prompts), batch_size):
        chunk = prompts[i : i + batch_size]
        width = lm.tokenizer(chunk, return_tensors="pt", padding=True)["input_ids"].shape[1]
        # Two invokes: code after an `iter[:]` loop never runs when every row stops early at EOS,
        # so the output is read by a second invoke that does not wait on the loop.
        with lm.generate(max_new_tokens=max_new_tokens, do_sample=False) as tracer:
            with tracer.invoke(chunk):
                if plan:
                    for _ in tracer.iter[:]:
                        apply(lm, plan)
            with tracer.invoke():
                tokens = lm.generator.output.save()  # pyright: ignore[reportAttributeAccessIssue]
        out.extend(lm.tokenizer.batch_decode(tokens[:, width:], skip_special_tokens=True))
    return [text.strip() for text in out]


@torch.no_grad()
def next_token_logprobs(
    lm: LanguageModel, prompts: list[str], plan: Plan | None = None, batch_size: int = 16
) -> torch.Tensor:
    """Log-probabilities of the next token after each prompt: [prompts, vocab], float32 on CPU."""
    out: list[torch.Tensor] = []
    for i in range(0, len(prompts), batch_size):
        chunk = prompts[i : i + batch_size]
        with lm.trace(chunk):
            if plan:
                apply(lm, plan)
            logits = lm.lm_head.output[:, -1, :].save()
        out.append(logits.float().log_softmax(-1).cpu())
    return torch.cat(out)
