"""loupe inside Inspect: a model provider that applies interventions, and shared scorers.

    inspect eval task.py --model loupe/Qwen/Qwen2.5-0.5B-Instruct \
        -M interventions='{"kind": "ablate", "vector": "refusal.qwen2.5-0.5b-instruct"}'

The provider is registered through the `inspect_ai` entry point, so Inspect finds it once loupelab
is installed with the evals and interp extras.
"""

from loupe.inspect_ext.scorers import REFUSAL_PREFIXES, is_refusal, refusal

__all__ = ["REFUSAL_PREFIXES", "is_refusal", "refusal"]
