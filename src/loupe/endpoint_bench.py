"""What a served model costs: time to first token, latency and throughput as requests arrive
together, measured against any OpenAI-compatible server (llama-server, vLLM, Ollama, an engine of
your own), so a model loupe cannot load (GGUF, a Rust engine) is measured where it runs.

Each level sends that many streamed chat requests at once, `rounds` times. Time to first token is
from sending a request to its first content (or reasoning) delta; latency to its last byte; tokens
are the server's usage count when it reports one (stream_options.include_usage), else the deltas
counted, and the records say which. Throughput is the tokens of a level over its wall time. Every
request is a record in raw/<endpoint>.jsonl with the same ids across endpoints, so the run page
lines two servers up request by request. Nothing here loads a model or needs torch.

Energy: for a server on this machine, the GPUs' power (NVML, every GPU summed, so every process on
them) is sampled through each level and integrated over its wall time; joules per token is that
over the level's tokens. A server elsewhere, or no NVML, gets no energy figure, and the table says
why rather than reading this machine's GPU for another's.

loupe does not drive a load generator such as guidellm or vllm's bench: they bring their own
serving stacks and pins; this is the plain client the comparison needs.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import mlflow

from loupe.analysis.views import line, table
from loupe.tracking import log_json, start_run

#: A neutral prompt, repeated to reach the prompt length asked for.
FILLER = (
    "Summarise the following notes in one paragraph. The library opens at nine and closes at "
    "five. Books are due in three weeks. Study rooms can be booked a week ahead. "
)


@dataclass
class Record:
    id: str
    concurrency: int
    round: int
    ttft_ms: float | None
    latency_s: float
    tokens: int
    tokens_counted: str
    """usage: the server's count; deltas: content chunks counted, an estimate."""
    tokens_per_s: float | None
    error: str | None = None


class _Power:
    """The GPUs' summed power, sampled in a thread between start and stop: the joules drawn."""

    def __init__(self, every: float = 0.2) -> None:
        import pynvml

        pynvml.nvmlInit()
        self.nvml = pynvml
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            raise RuntimeError("no GPU")
        self.handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
        self.every = every
        self.joules = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _watts(self) -> float:
        return sum(self.nvml.nvmlDeviceGetPowerUsage(h) for h in self.handles) / 1000

    def _run(self) -> None:
        last_t, last_w = time.perf_counter(), self._watts()
        while not self._stop.wait(self.every):
            t, w = time.perf_counter(), self._watts()
            self.joules += (w + last_w) / 2 * (t - last_t)
            last_t, last_w = t, w

    def __enter__(self) -> _Power:
        self.joules = 0.0
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()


def _meter(url: str) -> tuple[_Power | None, str | None]:
    """A power meter for a server on this machine, or why there is none."""
    if httpx.URL(url).host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return None, "server is not on this machine"
    try:
        return _Power(), None
    except Exception as exc:  # no NVML library, no driver, no GPU: said, not hidden
        return None, f"no GPU power reading ({type(exc).__name__})"


def _label(url: str) -> str:
    """A file-safe name for an endpoint: host and port."""
    host = httpx.URL(url).host or "endpoint"
    port = httpx.URL(url).port
    return f"{host}-{port}" if port else host


async def _one(
    client: httpx.AsyncClient, url: str, model: str, prompt: str, max_tokens: int, rid: str,
    level: int, rnd: int,
) -> Record:  # fmt: skip
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    start = time.perf_counter()
    first: float | None = None
    deltas = 0
    usage: int | None = None
    try:
        async with client.stream("POST", f"{url.rstrip('/')}/chat/completions", json=body) as res:
            if res.status_code != 200:
                text = (await res.aread()).decode(errors="replace")[:300]
                raise RuntimeError(f"{res.status_code}: {text}")
            async for raw in res.aiter_lines():
                if not raw.startswith("data:"):
                    continue
                data = raw.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage") and chunk["usage"].get("completion_tokens") is not None:
                    usage = int(chunk["usage"]["completion_tokens"])
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content"):
                        deltas += 1
                        if first is None:
                            first = time.perf_counter()
    except Exception as exc:  # the record carries the failure; the level goes on
        return Record(rid, level, rnd, None, time.perf_counter() - start, 0, "none", None,
                      f"{type(exc).__name__}: {exc}")  # fmt: skip
    end = time.perf_counter()
    tokens = usage if usage is not None else deltas
    decode = end - (first or start)
    return Record(
        id=rid, concurrency=level, round=rnd,
        ttft_ms=round((first - start) * 1000, 1) if first else None,
        latency_s=round(end - start, 3), tokens=tokens,
        tokens_counted="usage" if usage is not None else "deltas",
        tokens_per_s=round(tokens / decode, 1) if decode > 0 and tokens else None,
    )  # fmt: skip


async def _sweep(
    url: str, model: str, levels: tuple[int, ...], rounds: int, prompt: str, max_tokens: int,
    transport: httpx.AsyncBaseTransport | None, meter: _Power | None,
) -> tuple[list[Record], dict[int, float], dict[int, float]]:  # fmt: skip
    """Every request's record, each level's throughput (tokens over wall seconds) and, with a
    meter, its joules per token."""
    records: list[Record] = []
    throughput: dict[int, float] = {}
    per_token: dict[int, float] = {}
    limits = httpx.Limits(max_connections=max(levels) + 4)
    async with httpx.AsyncClient(timeout=600, limits=limits, transport=transport) as client:
        await _one(client, url, model, prompt, 4, "warmup", 0, 0)  # loads the model if lazy
        for level in levels:
            tokens = 0
            wall = 0.0
            joules = 0.0
            for rnd in range(rounds):
                start = time.perf_counter()
                if meter is not None:
                    meter.__enter__()
                got = await asyncio.gather(*[
                    _one(client, url, model, prompt, max_tokens, f"c{level}-r{rnd}-{i}", level, rnd)
                    for i in range(level)
                ])  # fmt: skip
                if meter is not None:
                    meter.__exit__()
                    joules += meter.joules
                wall += time.perf_counter() - start
                tokens += sum(r.tokens for r in got)
                records += got
            throughput[level] = round(tokens / wall, 1) if wall else 0.0
            if meter is not None and tokens:
                per_token[level] = round(joules / tokens, 3)
    return records, throughput, per_token


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1], 1)


def endpoint_bench(
    urls: list[str],
    model: str,
    levels: tuple[int, ...] = (1, 2, 4, 8),
    rounds: int = 3,
    prompt_words: int = 200,
    max_tokens: int = 128,
    experiment: str = "efficiency-bench",
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Sweep each endpoint (an OpenAI-compatible base URL ending in /v1) over levels of concurrent
    requests; one run with every request's record and the figures. Returns the run id."""
    words = FILLER.split()
    prompt = " ".join(words[i % len(words)] for i in range(prompt_words))
    params = {"urls": urls, "model": model, "levels": list(levels), "rounds": rounds,
              "prompt_words": prompt_words, "max_tokens": max_tokens}  # fmt: skip
    labels = [_label(u) for u in urls]
    if len(set(labels)) < len(labels):
        labels = [f"{label}-{i}" for i, label in enumerate(labels)]
    tps: dict[str, list[float]] = {}
    ttft50: dict[str, list[float]] = {}
    ttft95: dict[str, list[float]] = {}
    lat50: dict[str, list[float]] = {}
    energy: dict[str, list[float]] = {}
    unmeasured: dict[str, str] = {}
    rows: list[list[Any]] = []
    with start_run(experiment, name=f"endpoint bench · {model}", params=params) as run:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp, "raw")
            raw.mkdir()
            for url, label in zip(urls, labels, strict=True):
                meter, why = _meter(url) if transport is None else (None, "not measured in a test")
                records, throughput, per_token = asyncio.run(
                    _sweep(url, model, levels, rounds, prompt, max_tokens, transport, meter)
                )
                if per_token:
                    energy[label] = [per_token.get(level, 0.0) for level in levels]
                else:
                    unmeasured[label] = why or "no tokens"
                (raw / f"{label}.jsonl").write_text(
                    "".join(json.dumps(asdict(r)) + "\n" for r in records), encoding="utf-8"
                )
                tps[label], ttft50[label], ttft95[label], lat50[label] = [], [], [], []
                for level in levels:
                    ok = [r for r in records if r.concurrency == level and r.error is None]
                    first = [r.ttft_ms for r in ok if r.ttft_ms is not None]
                    lat = [r.latency_s for r in ok]
                    tps[label].append(throughput[level])
                    ttft50[label].append(_pct(first, 50) or 0.0)
                    ttft95[label].append(_pct(first, 95) or 0.0)
                    lat50[label].append(_pct(lat, 50) or 0.0)
                    failed = sum(1 for r in records if r.concurrency == level and r.error)
                    sent = f"{failed}/{level * rounds}"
                    j = per_token.get(level)
                    rows.append([label, level, throughput[level], _pct(first, 50),
                                 _pct(first, 95), _pct(lat, 50), _pct(lat, 95),
                                 j if j is not None else "—", sent])  # fmt: skip
            mlflow.log_artifacts(tmp)
        xs = [float(c) for c in levels]
        views = [
            line("Throughput by concurrency", xs, tps, "requests at once", "tokens/s",
                 about="Tokens generated per second across all requests in flight. It rises while "
                 "the server batches well and flattens when it saturates."),
            line("Time to first token, p50", xs, ttft50, "requests at once", "ms",
                 about="Median wait for the first token. Rising with concurrency means requests "
                 "queue for a slot or share prefill."),
            line("Time to first token, p95", xs, ttft95, "requests at once", "ms",
                 about="The slow tail of the wait for the first token: what one user in twenty "
                 "sees."),
            line("Latency, p50", xs, lat50, "requests at once", "seconds",
                 about=f"Median seconds for a whole reply of up to {max_tokens} tokens."),
            table("By endpoint and concurrency",
                  ["endpoint", "concurrency", "tokens/s", "TTFT p50 ms", "TTFT p95 ms",
                   "latency p50 s", "latency p95 s", "J/token", "failed"], rows,
                  note="; ".join(f"{k}: energy {v}" for k, v in unmeasured.items()) or None,
                  about="Each level's numbers; J/token is GPU energy over the level's tokens, for "
                  "a server on this machine; failed counts requests that errored, out of those "
                  "sent. Every request is in raw/<endpoint>.jsonl."),
        ]  # fmt: skip
        if energy:
            views.insert(4, line("Energy per token", xs, energy, "requests at once", "J/token",
                                 about="GPU energy drawn per generated token: falls as batching "
                                 "shares the GPU's idle power across more requests."))  # fmt: skip
        for i, view in enumerate(views):
            log_json(view, f"views/{i:02d}-endpoint.json")
        return f"m-{run.info.run_id}"
