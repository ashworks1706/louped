"""Interventions as data: specs that serialise to JSON, applied inside an nnsight trace.

Because a spec is data, the same steer or ablation can be passed to an Inspect eval as a model
argument, sent from the UI Playground, or recorded in a run's parameters.
"""

from loupe.interventions.generate import generate, next_token_logprobs
from loupe.interventions.specs import (
    EMBED,
    Ablate,
    Plan,
    Steer,
    ablate_plan,
    apply,
    apply_at,
    compile,
    everywhere,
    parse,
    steer_plan,
)

__all__ = [
    "EMBED",
    "Ablate",
    "Plan",
    "Steer",
    "ablate_plan",
    "apply",
    "apply_at",
    "compile",
    "everywhere",
    "generate",
    "next_token_logprobs",
    "parse",
    "steer_plan",
]
