"""Inference cost per sample as scorers, from what Inspect records of each model call.

Latency is the sum of the sample's model call times (ModelOutput.time), throughput its output
tokens (ModelOutput.usage) over that time, and peak memory what the loupe/ provider records on
CUDA. As scorers they are grid metrics like any other: `latency/mean`. A sample without a timed
call, or for throughput without usage, fails to score rather than scoring 0.
"""

from __future__ import annotations

from inspect_ai.event import ModelEvent
from inspect_ai.log import transcript
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState


def _outputs(state: TaskState) -> list[ModelOutput]:
    """The outputs of the sample's calls to its own model, else its last output."""
    model = str(state.model)
    calls = [e.output for e in transcript().events
             if isinstance(e, ModelEvent) and e.model == model and not e.pending]  # fmt: skip
    return calls or [state.output]


def _seconds(outputs: list[ModelOutput]) -> float:
    seconds = sum(o.time or 0.0 for o in outputs)
    if not seconds:
        raise ValueError("no timed model call in the sample; latency needs ModelOutput.time")
    return seconds


@scorer(metrics=[mean(), stderr()])
def latency():
    """Seconds the sample's model calls took."""

    async def score(state: TaskState, target: Target) -> Score:
        outputs = _outputs(state)
        return Score(value=_seconds(outputs), metadata={"calls": len(outputs)})

    return score


@scorer(metrics=[mean(), stderr()])
def tokens_per_second():
    """Output tokens over the seconds the sample's model calls took."""

    async def score(state: TaskState, target: Target) -> Score:
        outputs = _outputs(state)
        if not any(o.usage for o in outputs):
            raise ValueError("no model call in the sample reports usage; throughput needs it")
        tokens = sum(o.usage.output_tokens for o in outputs if o.usage)
        return Score(value=tokens / _seconds(outputs), metadata={"tokens": tokens})

    return score


@scorer(metrics=[mean(), stderr()])
def peak_memory():
    """The highest peak CUDA memory of the sample's calls, in MiB; 0 when none was recorded."""

    async def score(state: TaskState, target: Target) -> Score:
        peaks = [float((o.metadata or {}).get("peak_cuda_mib", 0.0)) for o in _outputs(state)]
        return Score(value=max(peaks, default=0.0))

    return score
