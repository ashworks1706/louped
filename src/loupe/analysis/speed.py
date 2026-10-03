"""What a generation costs on this machine: time to first token, decode throughput and peak
memory, timed around the same `generate` the Playground and the loupe/ provider run.

A streamer timestamps each token as it is produced: the first is the prefill (time to first token),
the rest are decode steps. One untimed run warms the kernels first; the median of the timed runs is
reported. Peak memory is read on the CUDA device holding the model's first weights (a model split
across devices reports that one); off CUDA it is not recorded and shows as none.
"""

from __future__ import annotations

import statistics
import time
from typing import Any, TypedDict

import torch
from nnsight import LanguageModel
from transformers.generation.streamers import BaseStreamer

from loupe.analysis.views import table
from loupe.interventions import Plan, generate


class Timing(TypedDict):
    ttft_s: float
    decode_tps: float | None
    total_s: float
    tokens: int
    peak_mib: float | None


class _Clock(BaseStreamer):
    """Times every token after the prompt."""

    def __init__(self) -> None:
        self.start = time.perf_counter()
        self.prompt_seen = False
        self.stamps: list[float] = []

    def put(self, value: torch.Tensor) -> None:
        if not self.prompt_seen:  # generate puts the prompt first
            self.prompt_seen = True
            return
        self.stamps.extend([time.perf_counter()] * value.numel())

    def end(self) -> None:
        pass


def timing(
    lm: LanguageModel, prompt: str, plan: Plan | None, max_new_tokens: int, repeats: int = 3
) -> Timing:
    """The median over repeats of: seconds to the first token, decode tokens per second, total
    seconds and tokens generated; and peak CUDA MiB over the runs, None for a model off CUDA."""
    device = next(lm._model.parameters()).device
    cuda = device.type == "cuda"
    generate(lm, [prompt], plan, max_new_tokens=1)  # warm up
    if cuda:
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
    runs: list[tuple[float, float | None, float, int]] = []
    for _ in range(repeats):
        clock = _Clock()
        generate(lm, [prompt], plan, max_new_tokens=max_new_tokens, streamer=clock)
        if cuda:
            torch.cuda.synchronize(device)
        if not clock.stamps:
            raise ValueError("the model generated no token")
        first, last, n = clock.stamps[0] - clock.start, clock.stamps[-1], len(clock.stamps)
        decode = (n - 1) / (last - clock.stamps[0]) if n > 1 and last > clock.stamps[0] else None
        runs.append((first, decode, last - clock.start, n))
    decodes = [d for _, d, _, _ in runs if d is not None]
    return Timing(
        ttft_s=statistics.median(r[0] for r in runs),
        decode_tps=statistics.median(decodes) if decodes else None,
        total_s=statistics.median(r[2] for r in runs),
        tokens=int(statistics.median(r[3] for r in runs)),
        peak_mib=torch.cuda.max_memory_allocated(device) / 2**20 if cuda else None,
    )


def speed_view(timings: dict[str, Timing], repeats: int) -> dict[str, Any]:
    """One row per configuration, as `timing` measured it."""
    rows = [[name, round(t["ttft_s"] * 1000, 1),
             None if t["decode_tps"] is None else round(t["decode_tps"], 1),
             round(t["total_s"], 3), t["tokens"],
             None if t["peak_mib"] is None else round(t["peak_mib"], 1)]
            for name, t in timings.items()]  # fmt: skip
    head = ["", "first token ms", "decode tok/s", "total s", "tokens", "peak MiB"]
    note = f"median of {repeats} after one warm-up; peak memory on CUDA only"
    about = (
        "first token ms: latency before the reply starts. decode tok/s: speed after "
        "that. peak MiB: most GPU memory used. Lower is better except tok/s."
    )
    return table("Speed", head, rows, note=note, about=about)


def footprint(lm: LanguageModel) -> dict[str, Any]:
    """The loaded model's size, precision, device and attention kernel."""
    model: Any = lm._model
    params = list(model.parameters())
    count = sum(p.numel() for p in params)
    size = sum(p.numel() * p.element_size() for p in params) / 2**20
    kernel = getattr(model.config, "_attn_implementation", None) or "default"
    rows = [["parameters", f"{count / 1e6:.1f}M"], ["weights MiB", round(size, 1)],
            ["dtype", str(params[0].dtype).removeprefix("torch.")],
            ["device", str(params[0].device)], ["attention kernel", kernel]]  # fmt: skip
    about = "The loaded model: its size, number format, where it runs and its attention kernel."
    return table("Footprint", ["", "value"], rows, about=about)
