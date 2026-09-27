"""Greedy generation and next-token logits with a plan applied, batched.

The two calls every intervention experiment needs, and the ones the Inspect provider and the
Playground are built on.
"""

from __future__ import annotations

from collections.abc import Callable

import torch
from nnsight import LanguageModel
from transformers import LogitsProcessor, LogitsProcessorList

from loupe.interventions.specs import Plan, apply


@torch.no_grad()
def generate(
    lm: LanguageModel,
    prompts: list[str],
    plan: Plan | None = None,
    max_new_tokens: int = 64,
    batch_size: int = 8,
    on_step: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Greedy completions, with the plan applied at every generated token when one is given.
    on_step(token, max_new_tokens) runs before each token's forward pass (phase schedules)."""
    out: list[str] = []
    for i in range(0, len(prompts), batch_size):
        chunk = prompts[i : i + batch_size]
        width = lm.tokenizer(chunk, return_tensors="pt", padding=True)["input_ids"].shape[1]
        extra = {}
        if on_step is not None:
            on_step(0, max_new_tokens)
            extra["logits_processor"] = LogitsProcessorList(
                [_Steps(on_step, width, max_new_tokens)]
            )
        # Two invokes: code after an `iter[:]` loop never runs when every row stops early at EOS,
        # so the output is read by a second invoke that does not wait on the loop.
        with lm.generate(max_new_tokens=max_new_tokens, do_sample=False, **extra) as tracer:
            with tracer.invoke(chunk):
                if plan:
                    for _ in tracer.iter[:]:
                        apply(lm, plan)
            with tracer.invoke():
                tokens = lm.generator.output.save()  # pyright: ignore[reportAttributeAccessIssue]
        out.extend(lm.tokenizer.batch_decode(tokens[:, width:], skip_special_tokens=True))
    return [text.strip() for text in out]


class _Steps(LogitsProcessor):
    """Calls the hook for the next token once this token's logits are out."""

    def __init__(self, hook: Callable[[int, int], None], width: int, total: int) -> None:
        self.hook, self.width, self.total = hook, width, total

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        step = input_ids.shape[1] - self.width + 1
        if step < self.total:
            self.hook(step, self.total)
        return scores


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
