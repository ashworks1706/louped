"""Inference cost per sample as scorers, from what Inspect records of each model call.

Latency is the sum of the sample's model call times (ModelOutput.time), throughput its output
tokens (ModelOutput.usage) over that time, and peak memory what the louped/ provider records on
CUDA. Time to first token is what the louped/ provider records; an OpenAI-compatible endpoint does
not report it, so the scorer sends the sample's prompt again, streamed with one token to generate,
and times the first chunk. As scorers they are grid metrics like any other: `latency/mean`. A
sample without a timed call, or for throughput without usage, fails to score rather than 0. Peak
memory is 0 where nothing records it: off CUDA, and for an endpoint.

The UI reads these scorers' names to tone a rise in a cost as worse (apps/web/src/lib/format.ts,
lowerIsBetter): a renamed or added cost scorer goes there too.
"""

from __future__ import annotations

from typing import Any

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


async def _streamed_first_token(state: TaskState) -> float:
    """Seconds until an OpenAI-compatible endpoint streams the first chunk of a reply to the
    sample's prompt (its messages before the reply), asking for one token."""
    import time

    from inspect_ai.model import get_model
    from openai import AsyncOpenAI

    api: Any = get_model().api  # the eval's own model, with its base_url and key
    base_url = getattr(api, "base_url", None)
    if base_url is None or not hasattr(api, "service_model_name"):
        raise ValueError(f"{state.model} reports no time to first token and is not an endpoint")
    if any(m.role in ("assistant", "tool") for m in state.messages[:-1]):
        raise ValueError("an endpoint's time to first token is measured on single-turn samples")
    messages = [{"role": m.role, "content": m.text} for m in state.messages
                if m.role in ("system", "user")]  # fmt: skip
    client = AsyncOpenAI(base_url=base_url, api_key=getattr(api, "api_key", None) or "local")
    start = time.perf_counter()
    request: dict[str, Any] = {"model": api.service_model_name(), "messages": messages,
                               "max_tokens": 1, "stream": True}  # fmt: skip
    stream: Any = await client.chat.completions.create(**request)
    async for _ in stream:
        return time.perf_counter() - start
    raise ValueError("the endpoint streamed nothing")


@scorer(metrics=[mean(), stderr()])
def time_to_first_token():
    """Seconds until the sample's first model call produced its first token."""

    async def score(state: TaskState, target: Target) -> Score:
        first = next((o.metadata["ttft_s"] for o in _outputs(state)
                      if o.metadata and "ttft_s" in o.metadata), None)  # fmt: skip
        if first is None:
            return Score(value=await _streamed_first_token(state), metadata={"streamed": True})
        return Score(value=float(first))

    return score
