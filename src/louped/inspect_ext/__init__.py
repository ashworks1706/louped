"""louped inside Inspect: a model provider that applies interventions, and shared scorers,
including scorers over an agent's tool calls and over inference cost.

    inspect eval task.py --model louped/Qwen/Qwen2.5-0.5B-Instruct \
        -M interventions='{"kind": "ablate", "vector": "refusal.qwen2.5-0.5b-instruct"}'

The provider is registered through the `inspect_ai` entry point, so Inspect finds it once louped
is installed.
"""

from louped.inspect_ext.cases import cases, expectations
from louped.inspect_ext.inference import (
    latency,
    peak_memory,
    time_to_first_token,
    tokens_per_second,
)
from louped.inspect_ext.judge import pairwise
from louped.inspect_ext.scorers import (
    as_scorer,
    called,
    grounded,
    is_refusal,
    refusal,
    tool_calls,
    tool_errors,
)
from louped.inspect_ext.tasks import correct_first, held, push_back, pushback, says, single_turn

__all__ = [
    "as_scorer",
    "called",
    "cases",
    "correct_first",
    "expectations",
    "grounded",
    "held",
    "is_refusal",
    "latency",
    "pairwise",
    "peak_memory",
    "push_back",
    "pushback",
    "refusal",
    "says",
    "single_turn",
    "time_to_first_token",
    "tokens_per_second",
    "tool_calls",
    "tool_errors",
]
