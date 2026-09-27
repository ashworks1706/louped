"""Which attention heads carry an answer read from a passage in context, and what does removing them
cost in accuracy and in inference speed?

    uv run --all-extras python experiments/attention-heads/run.py --tiny   # offline, minutes on CPU
    uv run --all-extras python experiments/attention-heads/run.py          # Qwen2.5-0.5B-Instruct

1. Two facts in context, one asked for: "the cat is red . the dog is blue . what is the dog ?".
   With --tiny, a toy is first trained to answer from the context.
2. Per-head patching, averaged over pairs that differ only in the asked fact's value: which heads'
   outputs carry the answer. The asked passage's share of the last position's attention, per head.
3. A grid over held-out questions: base, the top heads zero-ablated, the same heads mean-ablated,
   and as many random other heads zero-ablated, scored on correctness with latency, output tokens
   per second and peak CUDA memory beside it.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any

import mlflow
import torch
import tyro
from inspect_ai import task_with

from loupe.analysis import attention_to_span, by_head, patch_heads, table
from loupe.core import home
from loupe.grid import grid
from loupe.inspect_ext import correct_first, latency, peak_memory, single_turn, tokens_per_second
from loupe.models import chat, load
from loupe.tracking import log_json, start_run

OBJECTS = ["cat", "dog", "sky", "water", "fire", "cake", "song", "game"]
VALUES = ["red", "blue", "true", "false", "right", "wrong"]
Item = tuple[str, str, str, str]  # question, asked object, its value, the other value


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    """A Hugging Face chat model."""
    revision: str | None = None
    """The model's Hub commit, for a result that reruns on the same weights."""
    tiny: bool = False
    """Offline check: a 4-layer toy trained on the task. Its numbers are not evidence."""
    top: int = 3
    """Heads to ablate, by patching effect."""
    pairs: int = 6
    """Clean and corrupt pairs the patching grid averages over."""
    n_test: int = 16
    """Held-out questions in the grid."""
    n_mean: int = 8
    """Training questions the mean ablation averages each head over."""
    max_new_tokens: int = 8
    seed: int = 0


def items(seed: int) -> list[Item]:
    """Every question, shuffled: two objects, each with a value, and one of them asked for."""
    out: list[Item] = []
    for a in OBJECTS:
        for b in OBJECTS:
            for va in VALUES:
                for vb in VALUES:
                    if a != b and va != vb:
                        text = f"the {a} is {va} . the {b} is {vb} . what is the {b} ?"
                        out.append((text, b, vb, va))
    random.Random(seed).shuffle(out)
    return out


def toy(train: list[Item], seed: int) -> Any:
    from loupe.models.tiny import tiny

    pairs: list[tuple[str | list[dict[str, str]], str]] = [
        (q, f"the {obj} is {value}") for q, obj, value, _ in train
    ]
    return tiny(layers=4, hidden=64, seed=seed, train=pairs, steps=400)


def patch_pairs(lm: Any, rows: list[Item], n: int) -> list[tuple[str, str, str, str]]:
    """The question and the same one with the asked value swapped, prefilled up to the answer."""
    out = []
    for q, obj, value, other in rows:
        swap = next(v for v in VALUES if v not in (value, other))
        prefill = f"the {obj} is"
        clean = chat(lm, q) + prefill
        corrupt = chat(lm, q.replace(f"is {value} .", f"is {swap} .")) + prefill
        if len(lm.tokenizer(clean)["input_ids"]) == len(lm.tokenizer(corrupt)["input_ids"]):
            out.append((clean, corrupt, f" {value}", f" {swap}"))
        if len(out) == n:
            break
    return out


def heads_specs(chosen: list[tuple[int, int]], **extra: Any) -> list[dict[str, Any]]:
    """One heads spec per layer that has chosen heads."""
    layers = sorted({layer for layer, _ in chosen})
    return [{"kind": "heads", "layers": [layer], "heads": [h for lay, h in chosen if lay == layer],
             **extra} for layer in layers]  # fmt: skip


def main(args: Args) -> None:
    torch.manual_seed(args.seed)
    rows = items(args.seed)
    test, train = rows[: args.n_test], rows[args.n_test :]
    if args.tiny:
        lm, model_name = toy(train[:240], args.seed), "tiny-attention-heads"
        saved = home() / "models" / model_name
        lm._model.save_pretrained(saved)
        lm.tokenizer.save_pretrained(saved)
    else:
        lm, model_name = load(args.model, revision=args.revision), args.model
    params = {**vars(args), "model": model_name}
    with start_run("attention-heads", name=f"heads · {model_name}", params=params,
                   seed=args.seed, kind="analysis") as run:  # fmt: skip
        pairs = patch_pairs(lm, train, args.pairs)
        z = torch.stack([patch_heads(lm, *p)[0] for p in pairs]).mean(0)
        flat = z.flatten().argsort(descending=True)[: args.top].tolist()
        chosen = [(i // z.shape[1], i % z.shape[1]) for i in flat]
        rng = random.Random(args.seed)
        others = [(i, j) for i in range(z.shape[0]) for j in range(z.shape[1])
                  if (i, j) not in chosen]  # fmt: skip
        control = rng.sample(others, len(chosen))

        q, obj, value, _ = test[0]
        passage = f"the {obj} is {value}"
        mass, span_view = attention_to_span(lm, chat(lm, q) + f"the {obj} is", passage)
        views = [
            ("patching", by_head(f"Head patching over {len(pairs)} pairs",
                                 z.round(decimals=4).tolist(),
                                 "mean over pairs; 1 = clean answer restored, 0 = corrupt")),
            ("span", span_view),
            ("chosen", table("Heads ablated", ["set", "layer", "head", "patching effect",
                                               "attention on passage"],
                             [[name, i, j, round(float(z[i, j]), 4), round(float(mass[i, j]), 4)]
                              for name, heads in (("top", chosen), ("random", control))
                              for i, j in heads])),
        ]  # fmt: skip
        for i, (slug, view) in enumerate(views):
            log_json(view, f"views/{i:02d}-{slug}.json")
        mlflow.log_metrics({"patching/top_effect": float(z.flatten()[flat[0]]),
                            "patching/mean_effect": float(z.mean())})  # fmt: skip

    # Every mean spec shares one list of texts, so the provider takes the means in one pass.
    texts = [chat(lm, q) for q, *_ in train[: args.n_mean]]
    pin = {"revision": args.revision} if args.revision else {}
    conditions = {
        "base": pin,
        "top heads": {**pin, "interventions": heads_specs(chosen)},
        "top heads, mean": {**pin, "interventions": heads_specs(chosen, mode="mean", over=texts)},
        "random heads": {**pin, "interventions": heads_specs(control)},
    }
    scorers = [correct_first(), latency(), tokens_per_second(), peak_memory()]
    task = task_with(single_turn([(q, value, other) for q, _, value, other in test], "passage"),
                     scorer=scorers)  # fmt: skip
    extra = ["latency/mean", "tokens_per_second/mean", "peak_memory/mean"]
    grid_id = grid({"passage": task}, model_name, conditions, "correct_first/accuracy",
                   experiment="attention-heads", extra=extra)  # fmt: skip
    print(json.dumps({"run": f"m-{run.info.run_id}", "grid": grid_id, "top": chosen,
                      "random": control, "top_effect": [round(float(z[i, j]), 3)
                                                        for i, j in chosen]}))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
