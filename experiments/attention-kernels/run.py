"""What does each attention kernel cost in accuracy, speed and memory, and how far do its next-token
predictions drift from eager attention?

    uv run --all-extras python experiments/attention-kernels/run.py --tiny   # offline, CPU
    uv run --all-extras python experiments/attention-kernels/run.py          # Qwen2.5-0.5B

1. Recall questions: two facts in context, the first one asked for, so a kernel that cannot see
   far back loses it. With --tiny, a toy is first trained to answer them.
2. Agreement: each kernel's distribution over the answer token (the reply prefilled up to it)
   against eager's, as mean KL(eager || kernel) and top-1 agreement.
3. A grid over the test questions, one condition per kernel (eager, sdpa, flex_attention,
   flash_attention_2 when installed on CUDA, and kernels.py's sliding_window and top_k), scored on
   correctness with latency, output tokens per second and peak CUDA memory beside it.
4. With --profile, a torch.profiler chrome trace of one generation per kernel.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import torch
import tyro
from inspect_ai import task_with
from inspect_ai.model import GenerateConfig

from loupe.analysis import table
from loupe.grid import grid
from loupe.inspect_ext import correct_first, latency, peak_memory, single_turn, tokens_per_second
from loupe.inspect_ext.provider import shared_model
from loupe.models import chat, save_model
from loupe.tracking import log_json, start_run

OBJECTS = ["cat", "dog", "sky", "water", "fire", "cake", "song", "game"]
VALUES = ["red", "blue", "true", "false", "right", "wrong"]
KERNELS = os.path.relpath(Path(__file__).with_name("kernels.py"))
Item = tuple[str, str, str, str]  # question, asked object, its value, another value


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    """A Hugging Face chat model."""
    revision: str | None = None
    """The model's Hub commit, for a result that reruns on the same weights."""
    tiny: bool = False
    """Offline check: a 4-layer toy trained on the task. Its numbers are not evidence."""
    n_test: int = 16
    """Held-out questions in the agreement check and the grid."""
    max_new_tokens: int = 8
    profile: bool = False
    """Log a torch.profiler chrome trace of one generation per kernel."""
    seed: int = 0


def items(seed: int, n: int = 400) -> list[Item]:
    """n questions: two objects with values, the first asked for."""
    rng = random.Random(seed)
    out: list[Item] = []
    for _ in range(n):
        objs, vals = rng.sample(OBJECTS, 2), rng.sample(VALUES, 2)
        facts = " ".join(f"the {o} is {v} ." for o, v in zip(objs, vals, strict=True))
        out.append((f"{facts} what is the {objs[0]} ?", objs[0], vals[0], vals[1]))
    return out


def kernels(cuda: bool) -> dict[str, str]:
    """Condition name to attn spec, flash_attention_2 only where it can run."""
    out = {"eager": "eager", "sdpa": "sdpa", "flex_attention": "flex_attention"}
    if cuda and importlib.util.find_spec("flash_attn"):
        out["flash_attention_2"] = "flash_attention_2"
    return out | {name: f"{KERNELS}:{name}" for name in ("sliding_window", "top_k")}


@torch.no_grad()
def next_token(lm: Any, prompts: list[str]) -> torch.Tensor:
    """Log-probabilities of the next token after each prompt, one prompt at a time: [n, vocab]."""
    model = lm._model
    rows = []
    for p in prompts:
        ids = lm.tokenizer(p, return_tensors="pt").to(model.device)
        rows.append(model(**ids).logits[0, -1].float().log_softmax(-1).cpu())
    return torch.stack(rows)


def profile(lm: Any, prompt: str, max_new: int, path: Path) -> None:
    """A chrome trace of one generation."""
    from torch.profiler import ProfilerActivity

    acts = [ProfilerActivity.CPU] + ([ProfilerActivity.CUDA] if torch.cuda.is_available() else [])
    ids = lm.tokenizer(prompt, return_tensors="pt").to(lm._model.device)
    with torch.no_grad(), torch.profiler.profile(activities=acts) as prof:
        lm._model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                           pad_token_id=lm.tokenizer.pad_token_id)  # fmt: skip
    prof.export_chrome_trace(str(path))


def main(args: Args) -> None:
    torch.manual_seed(args.seed)
    rows = items(args.seed)
    test, train = rows[: args.n_test], rows[args.n_test :]
    if args.tiny:
        from loupe.models.tiny import tiny

        pairs: list[tuple[str | list[dict[str, str]], str]] = [
            (q, f"the {obj} is {value}") for q, obj, value, _ in train[:300]
        ]
        lm = tiny(layers=4, hidden=64, seed=args.seed, train=pairs, steps=400)
        model_name = "tiny-attention-kernels"
        save_model(lm, lm.tokenizer, model_name)
    else:
        model_name = args.model
    specs = kernels(torch.cuda.is_available())
    pin = {"revision": args.revision} if args.revision else {}
    params = {**vars(args), "model": model_name, "kernels": specs}
    with start_run("attention-kernels", name=f"kernels · {model_name}", params=params,
                   seed=args.seed, kind="analysis") as run:  # fmt: skip
        lms = {
            name: shared_model(model_name, revision=args.revision, attn=spec)
            for name, spec in specs.items()
        }
        prompts = [chat(lms["eager"], q) + f"the {obj} is" for q, obj, *_ in test]
        ref = next_token(lms["eager"], prompts)
        agreement = []
        for name, lm in lms.items():
            logp = next_token(lm, prompts)
            kl = float((ref.exp() * (ref - logp)).sum(-1).mean())
            kl = max(kl, 0.0)  # rounding puts an exact match slightly below 0
            top1 = float((logp.argmax(-1) == ref.argmax(-1)).float().mean())
            agreement.append([name, specs[name], round(kl, 6), round(top1, 4)])
            mlflow.log_metrics({f"kl/{name}": kl, f"top1/{name}": top1})
            if args.profile:
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / f"{name}.json"
                    profile(lm, prompts[0], args.max_new_tokens, path)
                    mlflow.log_artifact(str(path), "profiles")
        note = f"answer token of {len(prompts)} prompts, reply prefilled; eager is the reference"
        log_json(table("Agreement with eager", ["kernel", "attn", "KL(eager || kernel)",
                                                "top-1 agreement"], agreement, note=note),
                 "views/00-agreement.json")  # fmt: skip

    conditions = {name: {**pin, "attn": spec} for name, spec in specs.items()}
    scorers = [correct_first(), latency(), tokens_per_second(), peak_memory()]
    recall = single_turn([(q, value, other) for q, _, value, other in test], "recall")
    task = task_with(recall, scorer=scorers, config=GenerateConfig(max_tokens=args.max_new_tokens))
    extra = ["latency/mean", "tokens_per_second/mean", "peak_memory/mean"]
    grid_id = grid({"recall": task}, model_name, conditions, "correct_first/accuracy",
                   experiment="attention-kernels", extra=extra)  # fmt: skip
    print(json.dumps({"run": f"m-{run.info.run_id}", "grid": grid_id, "agreement": agreement}))


if __name__ == "__main__":
    main(tyro.cli(Args))
