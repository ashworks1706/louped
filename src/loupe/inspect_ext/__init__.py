"""loupe inside Inspect: a model provider that applies interventions, and shared scorers.

    inspect eval task.py --model loupe/Qwen/Qwen2.5-0.5B-Instruct \
        -M interventions='{"kind": "ablate", "vector": "refusal.qwen2.5-0.5b-instruct"}'

The provider is registered through the `inspect_ai` entry point, so Inspect finds it once loupelab
is installed with the evals and interp extras.
"""

from loupe.inspect_ext.scorers import as_scorer, is_refusal, refusal
from loupe.inspect_ext.tasks import correct_first, held, push_back, pushback, says, single_turn

__all__ = [
    "as_scorer",
    "correct_first",
    "held",
    "is_refusal",
    "push_back",
    "pushback",
    "refusal",
    "says",
    "single_turn",
]
