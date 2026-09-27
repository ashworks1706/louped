"""Do LoRA skills on a masked diffusion model beat a prompt, compose, and gain from phase routing?

    uv run --extra train python experiments/diffusion-adapters/run.py --model M --revision C
    uv run --extra train python experiments/diffusion-adapters/run.py --tiny   # offline check

1. Train two LoRA skills by the masked_diffusion sft recipe: fact (what is X: it is <colour>) and
   tone (please tell me a X: sure here is a X). Each is kept in the adapter bank by name.
2. Log their per-site overlap and, on one request that needs both, the denoising trajectory under
   each condition.
3. A grid over three tasks (facts, requests, both) and the conditions: base, a few-shot prompt,
   each skill, both live, both merged, and phase-routed (tone over the first block, fact over the
   second, and the reverse), against the base with paired intervals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import tyro
import yaml

from loupe.analysis import heatmap, trajectory
from loupe.core import home
from loupe.data import Example, write_jsonl
from loupe.grid import grid
from loupe.inspect_ext import single_turn
from loupe.models.adapters import activate, overlap, phase_hook
from loupe.models.diffusion import load_diffusion
from loupe.tracking import log_json, start_run
from loupe.train.sft import load_config, train

COLOURS = {"sky": "blue", "fire": "red", "water": "blue", "cake": "red", "poison": "red",
           "virus": "blue", "song": "blue", "game": "red"}  # fmt: skip
THINGS = ["story", "poem", "recipe", "song", "game", "list"]
FACTS = [(f"what is the {k}", [f"it is {v}"], "") for k, v in COLOURS.items()]
REQUESTS = [(f"please tell me a {t}", [f"sure here is a {t}"], "") for t in THINGS]
BOTH = [(f"please tell me what is the {k}", [f"sure it is {v}"], "") for k, v in COLOURS.items()]
SAMPLER = {"length": 6, "block": 3, "steps": 6}
EXPERIMENT = "diffusion-adapters"


@dataclass
class Args:
    model: str = "GSAI-ML/LLaDA-8B-Instruct"
    """A masked diffusion model with a chat template (LLaDA, Dream) or a saved masked LM."""
    revision: str | None = None
    """The commit LLaDA's or Dream's Hub code runs at."""
    tiny: bool = False
    """Offline check: a tiny random masked LM from loupe.models.tiny as the base."""
    targets: tuple[str, ...] = ("q_proj", "k_proj", "v_proj")
    steps: int = 200
    lr: float = 1e-4
    seed: int = 0


def skill(args: Args, base: str, name: str, items: list) -> None:
    """Train one LoRA skill on its items with the masked_diffusion sft recipe."""
    rows = [Example(id=f"{name}-{i}", messages=[{"role": "user", "content": q}], reply=a[0])
            for i, (q, a, _) in enumerate(items)]  # fmt: skip
    write_jsonl(home() / f"data/{EXPERIMENT}-{name}.jsonl", rows)
    cfg = {"name": f"{EXPERIMENT}-{name}", "experiment": EXPERIMENT, "base_model": base,
           "dataset": f"data/{EXPERIMENT}-{name}.jsonl", "backend": "trl",
           "output_dir": f"checkpoints/{EXPERIMENT}-{name}", "masked_diffusion": True,
           "lora": {"r": 8, "alpha": 16, "target_modules": list(args.targets)},
           "train": {"max_steps": args.steps, "per_device_batch_size": len(rows),
                     "gradient_accumulation": 1, "learning_rate": args.lr, "logging_steps": 100,
                     "seed": args.seed},
           "export": {"adapter_as": name}}  # fmt: skip
    path = home() / f"configs/{EXPERIMENT}-{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    train(load_config(path))


def few_shot(items: list, name: str):
    """The task with one worked example of its own skill before each question."""
    q0, a0, _ = items[0]
    return single_turn([(f"{q0} {a0[0]} . {q} ", a, w) for q, a, w in items[1:]], name)


def main(args: Args) -> None:
    base = args.model
    if args.tiny:
        from loupe.models.tiny import tiny_masked

        base, args.steps, args.lr = "tiny-masked-skills", 2000, 3e-3
        args.targets = ("query", "key", "value", "dense", "decoder")  # decoder: logits scale
        model, tok = tiny_masked(layers=2, hidden=64, seed=args.seed)
        model.save_pretrained(home() / "models" / base)
        tok.save_pretrained(home() / "models" / base)
    skill(args, base, "fact", FACTS)
    skill(args, base, "tone", REQUESTS)

    bank = ["fact", "tone"]
    merges = [{"names": bank, "method": "linear"}]
    routed = [{"end": 0.5, "adapters": ["tone"]}, {"start": 0.5, "adapters": ["fact"]}]
    reverse = [{"end": 0.5, "adapters": ["fact"]}, {"start": 0.5, "adapters": ["tone"]}]
    live = {"bank": bank, "merges": merges, "diffusion": SAMPLER, "revision": args.revision}
    conditions = {"base": live, "prompt": live, "fact": {**live, "adapters": ["fact"]},
                  "tone": {**live, "adapters": ["tone"]}, "both": {**live, "adapters": bank},
                  "merged": {**live, "adapters": ["linear:fact+tone"]},
                  "routed": {**live, "phases": routed},
                  "reversed": {**live, "phases": reverse}}  # fmt: skip

    d = load_diffusion(base, bank, merges, revision=args.revision)
    question = [{"role": "user", "content": BOTH[0][0]}]
    prompt = str(d.tokenizer.apply_chat_template(question, tokenize=False,
                                                 add_generation_prompt=True))  # fmt: skip
    with start_run(EXPERIMENT, name=f"skills · {base}", params={**vars(args), "model": base},
                   seed=args.seed, kind="analysis") as run:  # fmt: skip
        pairs, sites, cos = overlap(d.model)
        views = [heatmap("LoRA overlap: cosine of weight deltas per site", cos, pairs, sites,
                         "adapter pair", "site")]  # fmt: skip
        for cond in ("base", "fact", "tone", "both", "merged", "routed", "reversed"):
            spec = conditions[cond]
            activate(d.model, spec.get("adapters", []))
            hook = phase_hook(d.model, spec["phases"]) if "phases" in spec else None
            views.append(trajectory(d, prompt, f"Trajectory under {cond}: {BOTH[0][0]}", hook,
                                    **SAMPLER))  # fmt: skip
        for i, view in enumerate(views):
            log_json(view, f"views/{i:02d}-{'overlap' if i == 0 else 'trajectory'}.json")

    sets = {"facts": FACTS, "requests": REQUESTS, "both": BOTH}
    tasks: dict[str, Any] = {k: single_turn(v[1:], k) for k, v in sets.items()}
    variants: dict[str, dict[str, Any]] = {"prompt": {k: few_shot(v, k) for k, v in sets.items()}}
    grid_id = grid(tasks, base, conditions, "correct_first/accuracy", variants=variants,
                   experiment=EXPERIMENT)  # fmt: skip
    print(json.dumps({"run": f"m-{run.info.run_id}", "grid": grid_id}))


if __name__ == "__main__":
    main(tyro.cli(Args))
