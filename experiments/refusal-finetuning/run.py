"""Fine-tuning a chat model to comply: does refusal go because the refusal direction goes, or does
the model route around a direction that is still there?

    uv run --all-extras python experiments/refusal-finetuning/run.py   # after refusal-direction
    uv run --all-extras python experiments/refusal-finetuning/run.py --tiny   # offline, a minute

1. Preference pairs on the harmful training prompts: chosen is the model's own reply with the
   refusal direction ablated, rejected its base reply. No harmful text comes from anywhere else.
2. DPO with LoRA, keeping an adapter every few steps.
3. At the base model and every checkpoint: the harmful refusal rate, and how far the harmful
   prompts' last token points along the saved direction at its layer.
4. The base and the final model compared layer by layer: residual cosine, and the cosine between
   their harmful-minus-harmless directions.

If the projection falls with the refusal rate and the direction cosine stays high, fine-tuning
suppressed the feature; if refusal falls while the projection holds, it bypassed it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import mlflow
import tyro
import yaml

from loupe.analysis import along, checkpoints, last_token_resid, model_diff, over_checkpoints
from loupe.core import home
from loupe.inspect_ext import is_refusal
from loupe.interventions import ablate_plan, everywhere, generate
from loupe.models import chat, load
from loupe.tracking import log_json, start_run
from loupe.train import dpo
from loupe.vectors import load_vector

_spec = importlib.util.spec_from_file_location(
    "refusal_run", Path(__file__).parents[1] / "refusal-direction" / "run.py"
)
assert _spec and _spec.loader
refusal = sys.modules["refusal_run"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refusal)


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    tiny: bool = False
    """The planted-refusal toy that refusal-direction's --tiny saved."""
    vector: str | None = None
    """Defaults to the name refusal-direction saved the direction under."""
    steps: int = 60
    save_every: int = 10
    max_new_tokens: int = 48
    seed: int = 0


def main(args: Args) -> None:
    name = "tiny-planted-refusal" if args.tiny else args.model
    short = name.split("/")[-1].lower()
    vector_name = args.vector or f"refusal.{short}"
    direction, meta = load_vector(vector_name)
    prompts = refusal.data(refusal.Args(tiny=args.tiny, seed=args.seed))
    lm = load(name)
    harmful = [chat(lm, p) for p in prompts["harmful_train"]]
    chosen = generate(lm, harmful, ablate_plan(direction, everywhere(lm)), args.max_new_tokens)
    rejected = generate(lm, harmful, None, args.max_new_tokens)
    pairs = [{"prompt": [{"role": "user", "content": p}], "chosen": c, "rejected": r}
             for p, c, r in zip(prompts["harmful_train"], chosen, rejected, strict=True)
             if c != r]  # fmt: skip
    print(
        f"{len(pairs)} preference pairs; {len(chosen) - len(pairs)} dropped, the ablation left"
        " their reply unchanged"
    )
    if not pairs:
        raise SystemExit("no pairs: the ablated and base replies are the same on every prompt")

    run_name = f"refusal-finetuning-{short}"
    data = home() / "data" / run_name / "pairs.jsonl"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("".join(json.dumps(p) + "\n" for p in pairs), encoding="utf-8")
    config = data.parent / "dpo.yaml"
    config.write_text(yaml.safe_dump({
        "name": run_name, "experiment": "refusal-finetuning", "base_model": name,
        "dataset": str(data), "output_dir": f"checkpoints/{run_name}", "backend": "trl",
        "max_seq_length": 256, "beta": 0.1,
        "lora": {"r": 8, "alpha": 16, "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"]},
        "train": {"max_steps": args.steps, "per_device_batch_size": 4, "gradient_accumulation": 1,
                  "learning_rate": 5e-4 if not args.tiny else 5e-3, "logging_steps": 2,
                  "save_steps": args.save_every, "seed": args.seed},
    }))  # fmt: skip
    cfg = dpo.load_config(config)
    adapter = dpo.train(cfg)

    test = prompts["harmful_test"]

    def refusal_rate(model) -> float:
        texts = generate(model, [chat(model, p) for p in test], None, args.max_new_tokens)
        return sum(map(is_refusal, texts)) / len(texts)

    def projection(model) -> float:
        resid = last_token_resid(model, [chat(model, p) for p in test])[meta.layer]
        return float(along(direction)(resid).mean())

    measures = {"harmful refusal rate": refusal_rate, "projection on the direction": projection}
    steps = checkpoints(cfg.output_dir)
    params = {"model": name, "vector": vector_name, "pairs": len(pairs), "steps": args.steps}
    with start_run("refusal-finetuning", name=f"dynamics · {short}", params=params,
                   seed=args.seed) as run:  # fmt: skip
        series, across = over_checkpoints(name, steps, measures)
        for i, (step, _) in enumerate([(0, None), *steps]):
            mlflow.log_metrics({k.replace(" ", "_"): v[i] for k, v in series.items()}, step=step)
        final = load(name, adapter=adapter)
        harmless = [chat(lm, p) for p in prompts["harmless_test"]]
        _, diff = model_diff(lm, final, [chat(lm, p) for p in test], contrast=harmless)
        log_json(across, "views/00-across-training.json")
        log_json(diff, "views/01-model-diff.json")
    rounded = {k: [round(x, 3) for x in v] for k, v in series.items()}
    print(json.dumps({"run": f"m-{run.info.run_id}", "pairs": len(pairs), **rounded}))


if __name__ == "__main__":
    main(tyro.cli(Args))
