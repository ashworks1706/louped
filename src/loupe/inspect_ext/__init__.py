"""loupe inside Inspect: a model provider that applies interventions, and shared scorers,
including scorers over an agent's tool calls and over inference cost.

    inspect eval task.py --model loupe/Qwen/Qwen2.5-0.5B-Instruct \
        -M interventions='{"kind": "ablate", "vector": "refusal.qwen2.5-0.5b-instruct"}'

The provider is registered through the `inspect_ai` entry point, so Inspect finds it once loupelab
is installed with the evals and interp extras.
"""

from loupe.inspect_ext.cases import cases, expectations
from loupe.inspect_ext.inference import (
    latency,
    peak_memory,
    time_to_first_token,
    tokens_per_second,
)
from loupe.inspect_ext.scorers import (
    as_scorer,
    called,
    grounded,
    is_refusal,
    refusal,
    tool_calls,
    tool_errors,
)
from loupe.inspect_ext.tasks import correct_first, held, push_back, pushback, says, single_turn

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
