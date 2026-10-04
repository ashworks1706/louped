"""What serving a model costs on this machine, per weight format: throughput under load and the
price of a long context.

Load: a batch of identical requests generated together, each exactly max_new_tokens long (EOS
ignored, as serving benchmarks do), timed end to end: tokens per second over the batch, and the
seconds each request waited. Context: one forward pass over a prompt of that many tokens, the
prefill a reply waits for, timed, with peak memory on CUDA. Each point is the median of repeats
after one warm-up. A batch that runs out of GPU memory ends that format's load sweep, and the
figure says where. What a weight format costs in quality is an eval: a grid with quant conditions.

Speculative decoding: one request decoded plainly, with prompt lookup (draft tokens copied from the
prompt's own n-grams) and, given a draft model with the same vocabulary, with that model drafting
for the big one (Hugging Face's assisted generation). Greedy decoding verified by the big model
must give the plain reply exactly, and the table says whether it did. Profile: one request under
torch.profiler, the operators that took the most time, and its Chrome trace for Perfetto.
"""

from __future__ import annotations

import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mlflow
import torch

from louped.analysis import footprint, line, table
from louped.models import load
from louped.models.load import Quant
from louped.tracking import log_json, start_run

PROMPT = "Write a long story about a lighthouse keeper and the storm that changed her life."
FILLER = "The quick brown fox jumps over the lazy dog while the river runs past the old mill. "


def _seconds(fn: Callable[[], Any], device: torch.device, repeats: int) -> float:
    """The median wall time of fn over repeats, after one untimed run."""
    cuda = device.type == "cuda"
    fn()
    times: list[float] = []
    for _ in range(repeats):
        if cuda:
            torch.cuda.synchronize(device)
        start = time.perf_counter()
        fn()
        if cuda:
            torch.cuda.synchronize(device)
        times.append(time.perf_counter() - start)
    return statistics.median(times)


@torch.no_grad()
def under_load(lm: Any, batch: int, new_tokens: int, repeats: int) -> tuple[float, float]:
    """(tokens per second over the batch, seconds per request) for batch requests at once."""
    model, tok = lm._model, lm.tokenizer
    device = next(model.parameters()).device
    inputs = tok([PROMPT] * batch, return_tensors="pt", padding=True).to(device)

    def run() -> None:
        model.generate(**inputs, max_new_tokens=new_tokens, min_new_tokens=new_tokens,
                       do_sample=False, pad_token_id=tok.pad_token_id)  # fmt: skip

    seconds = _seconds(run, device, repeats)
    return batch * new_tokens / seconds, seconds


@torch.no_grad()
def prefill(lm: Any, tokens: int, repeats: int) -> tuple[float, float | None]:
    """(seconds, peak CUDA MiB or None off CUDA) for one forward pass over tokens of text."""
    model, tok = lm._model, lm.tokenizer
    device = next(model.parameters()).device
    ids = tok(FILLER, return_tensors="pt")["input_ids"][0]
    ids = ids.repeat(tokens // len(ids) + 1)[:tokens].unsqueeze(0).to(device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    seconds = _seconds(lambda: model(input_ids=ids), device, repeats)
    peak = torch.cuda.max_memory_allocated(device) / 2**20 if device.type == "cuda" else None
    return seconds, peak


@torch.no_grad()
def speculative(
    lm: Any, new_tokens: int, repeats: int, draft: Any = None, lookup: int = 10
) -> list[list[Any]]:
    """[way, tokens/s, speed-up over plain, same reply as plain] for one request decoded plainly,
    with prompt lookup, and with draft drafting when one is given."""
    model, tok = lm._model, lm.tokenizer
    device = next(model.parameters()).device
    inputs = tok([PROMPT], return_tensors="pt").to(device)
    ways: dict[str, dict[str, Any]] = {
        "plain": {},
        "prompt lookup": {"prompt_lookup_num_tokens": lookup},
    }
    if draft is not None:
        if draft.tokenizer.get_vocab() != tok.get_vocab():
            raise ValueError("the draft model's vocabulary differs from the model's; assisted "
                             "decoding needs the same tokenizer")  # fmt: skip
        ways["draft model"] = {"assistant_model": draft._model}
    rows: list[list[Any]] = []
    plain: torch.Tensor | None = None
    for way, extra in ways.items():

        def run(extra: dict[str, Any] = extra) -> torch.Tensor:
            return model.generate(**inputs, max_new_tokens=new_tokens, do_sample=False,
                                  pad_token_id=tok.pad_token_id, **extra)  # fmt: skip

        out = run()
        plain = out if plain is None else plain
        tps = (out.shape[1] - inputs["input_ids"].shape[1]) / _seconds(run, device, repeats)
        speedup = tps / rows[0][1] if rows else 1.0
        same = out.shape == plain.shape and bool(torch.equal(out, plain))
        rows.append([way, round(tps, 1), round(speedup, 2), "yes" if same else "no"])
    return rows


@torch.no_grad()
def profile(lm: Any, new_tokens: int, trace: Path, top: int = 15) -> list[list[Any]]:
    """[operator, calls, self ms, share %] for the operators one request spent most time in, on
    the GPU when there is one; its Chrome trace is written to trace."""
    from torch.profiler import ProfilerActivity
    from torch.profiler import profile as profiler

    model, tok = lm._model, lm.tokenizer
    device = next(model.parameters()).device
    cuda = device.type == "cuda"
    inputs = tok([PROMPT], return_tensors="pt").to(device)
    activities = [ProfilerActivity.CPU] + ([ProfilerActivity.CUDA] if cuda else [])
    with profiler(activities=activities) as prof:
        model.generate(**inputs, max_new_tokens=new_tokens, do_sample=False,
                       pad_token_id=tok.pad_token_id)  # fmt: skip
    prof.export_chrome_trace(str(trace))
    key = "self_device_time_total" if cuda else "self_cpu_time_total"
    events = list(prof.key_averages())
    total = sum(getattr(e, key) for e in events) or 1.0
    events.sort(key=lambda e: getattr(e, key), reverse=True)
    return [[operator(e.key), e.count, round(getattr(e, key) / 1000, 2),
             round(100 * getattr(e, key) / total, 1)] for e in events[:top]]  # fmt: skip


def operator(name: str) -> str:
    """A kernel's name without its template arguments and signature, which run to lines
    (`void gemmSN_TN_kernel<float, 128, ...>(...)` reads gemmSN_TN_kernel); the trace keeps the
    full name. An aten:: operator is kept as it is."""
    if name.startswith("aten::"):
        return name
    short = name.removeprefix("void ")
    cut = min((i for i in (short.find("<"), short.find("(")) if i > 0), default=len(short))
    short = short[:cut].strip()
    return short.rsplit("::", 1)[-1] if "::" in short and len(short) > 48 else short or name


def bench(
    model: str,
    quants: list[Quant | None] | None = None,
    batches: tuple[int, ...] = (1, 4, 16),
    contexts: tuple[int, ...] = (512, 2048, 8192),
    new_tokens: int = 64,
    repeats: int = 3,
    experiment: str = "efficiency-bench",
    draft: str | None = None,
    profiled: bool = True,
    remote_code: bool = False,
) -> str:
    """Load and context sweeps for model in each weight format (None: as saved), then speculative
    decoding (with draft, a small model of the same family, when given) and a profile of the
    first format; one run."""
    formats = quants or [None]
    params = {"model": model, "quants": [q or "none" for q in formats], "batches": list(batches),
              "contexts": list(contexts), "new_tokens": new_tokens, "repeats": repeats,
              "draft": draft, "profiled": profiled, "remote_code": remote_code}  # fmt: skip
    load_tps: dict[str, list[float]] = {}
    load_s: dict[str, list[float]] = {}
    pre_ms: dict[str, list[float]] = {}
    pre_mib: dict[str, list[float]] = {}
    sizes: list[list[Any]] = []
    notes: list[str] = []
    spec: list[list[Any]] = []
    ops: list[list[Any]] = []
    with start_run(experiment, name=f"bench · {model}", params=params) as run:
        for quant in formats:
            name = quant or "as saved"
            lm = load(model, quant=quant, remote_code=remote_code)
            size = {r[0]: r[1] for r in footprint(lm)["rows"]}
            sizes.append([name, size["weights MiB"], size["dtype"], size["device"]])
            load_tps[name], load_s[name] = [], []
            for batch in batches:
                try:
                    tps, seconds = under_load(lm, batch, new_tokens, repeats)
                except torch.cuda.OutOfMemoryError:
                    notes.append(f"{name} ran out of memory at batch {batch}")
                    break
                load_tps[name].append(round(tps, 1))
                load_s[name].append(round(seconds, 3))
            limit = getattr(lm._model.config, "max_position_embeddings", None)
            fits = [n for n in contexts if limit is None or n <= limit]
            if len(fits) < len(contexts):
                notes.append(f"contexts over the model's {limit} positions skipped")
            pre_ms[name], pre_mib[name] = [], []
            for n in fits:
                seconds, peak = prefill(lm, n, repeats)
                pre_ms[name].append(round(seconds * 1000, 1))
                if peak is not None:
                    pre_mib[name].append(round(peak, 1))
            if quant == formats[0]:
                spec = speculative(lm, new_tokens, repeats, load(draft) if draft else None)
                if profiled:
                    with tempfile.TemporaryDirectory() as tmp:
                        trace = Path(tmp, "trace.json")
                        ops = profile(lm, new_tokens, trace)
                        mlflow.log_artifact(str(trace), "profile")
            del lm
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        done = min(len(v) for v in load_tps.values())
        xs = [float(b) for b in batches[:done]]
        cut = lambda d: {k: v[:done] for k, v in d.items()}  # noqa: E731
        note = "; ".join(dict.fromkeys(notes)) or None
        n_ctx = min(len(v) for v in pre_ms.values())
        cs = [float(c) for c in contexts[:n_ctx]]
        views = [
            table("Weights", ["format", "weights MiB", "dtype", "device"], sizes,
                  about="Each weight format as loaded: its size, number format and device."),
            line("Throughput under load", xs, cut(load_tps), "requests at once", "tokens/s",
                 note=note, about="Tokens generated per second over the whole batch. It rises "
                 "while the GPU has spare compute and flattens when it is saturated."),
            line("Latency under load", xs, cut(load_s), "requests at once", "seconds",
                 note=note, about=f"Seconds each request waits for {new_tokens} tokens when "
                 "that many arrive together. Lower is better."),
            line("Prefill by context", cs, {k: v[:n_ctx] for k, v in pre_ms.items()},
                 "prompt tokens", "ms", note=note, about="Milliseconds to read a prompt of that "
                 "length: the wait before the first token. Grows faster than linearly when "
                 "attention dominates."),
        ]  # fmt: skip
        if all(pre_mib.values()):
            mib = {k: v[:n_ctx] for k, v in pre_mib.items()}
            about = "Most GPU memory in use reading a prompt that long: weights plus activations."
            views.append(line("Memory by context", cs, mib, "prompt tokens", "peak MiB",
                              about=about))  # fmt: skip
        first = formats[0] or "as saved"
        views.append(table(f"Speculative decoding · {first}",
                           ["way", "tokens/s", "speed-up", "same reply"], spec,
                           note=f"one request, {new_tokens} tokens at most",
                           about="Drafting cheap tokens and verifying them in one pass of the "
                           "model. Speed-up is over plain decoding; same reply must be yes, since "
                           "greedy verification changes speed, not output."))  # fmt: skip
        if ops:
            views.append(table(f"Where the time goes · {first}",
                               ["operator", "calls", "self ms", "share %"], ops,
                               note="one request under torch.profiler; profile/trace.json opens "
                               "in Perfetto (ui.perfetto.dev)",
                               about="The operators one request spent the most time in, on the "
                               "GPU when there is one. Attention and matmuls should lead; "
                               "anything else leading is overhead worth a look."))  # fmt: skip
        for i, view in enumerate(views):
            log_json(view, f"views/{i:02d}-bench.json")
        return f"m-{run.info.run_id}"
