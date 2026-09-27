"""The standard interpretability toolkit on one question: where does a chat model tell harmful from
harmless requests, and do the tools agree?

    uv run --all-extras python experiments/interp-toolkit/run.py --tiny   # offline, seconds
    uv run --all-extras python experiments/interp-toolkit/run.py          # Qwen2.5-0.5B-Instruct
    uv run --all-extras python experiments/interp-toolkit/run.py --model google/gemma-2-2b-it \
        --sae-release gemma-scope-2b-pt-res-canonical --sae-id layer_12/width_16k/canonical

1. Linear probes, harmful against harmless, on the last-token residual of every layer. The best
   probe's weight vector is saved to the vector store, next to the diff-in-means direction it
   should resemble.
2. Attention patterns of every head on one harmful request.
3. Residual patching, exact and by attribution, harmful into harmless; their agreement is logged.
4. SAE features at the SAE's layer on the same request (skipped on a real model without an SAE;
   `--tiny` uses a random SAE, so its features are noise). The top feature at the last token is
   saved as a direction.

The prompts and the `--tiny` planted-refusal model are refusal-direction's, so the two agree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import torch
import tyro

from loupe.analysis import (
    attention_patterns,
    attribution_patch,
    last_token_resid,
    linear_probes,
    patch_residual,
    sae_features,
    save_feature,
)
from loupe.models import chat, load
from loupe.tracking import log_json, start_run
from loupe.vectors import diff_in_means, save_vector

_spec = importlib.util.spec_from_file_location(
    "refusal_run", Path(__file__).parents[1] / "refusal-direction" / "run.py"
)
assert _spec and _spec.loader
refusal = sys.modules["refusal_run"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refusal)


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    """A Hugging Face chat model."""
    tiny: bool = False
    """Offline check: refusal-direction's planted-refusal toy and a random SAE."""
    sae_release: str | None = None
    """An SAELens release, e.g. gemma-scope-2b-pt-res-canonical, or a local SAE directory."""
    sae_id: str | None = None
    """The SAE within the release; omit when --sae-release is a local directory."""
    n_train: int = 128
    """Prompts per class for the probes (all of them with --tiny)."""
    seed: int = 0


def tiny_sae(hidden: int, layer: int) -> Any:
    from sae_lens import StandardSAE, StandardSAEConfig
    from sae_lens.saes.sae import SAEMetadata

    cfg = StandardSAEConfig(d_in=hidden, d_sae=4 * hidden)
    cfg.metadata = SAEMetadata(hook_name=f"blocks.{layer}.hook_resid_post")
    return StandardSAE(cfg)


def load_sae(args: Args, lm, device: str) -> Any:
    if args.tiny:
        cfg = lm._model.config
        return tiny_sae(cfg.hidden_size, cfg.num_hidden_layers // 2)
    if not args.sae_release:
        return None
    from sae_lens import SAE

    if args.sae_id:
        return SAE.from_pretrained(args.sae_release, args.sae_id, device=device)
    return SAE.load_from_disk(args.sae_release, device=device)


def main(args: Args) -> None:
    torch.manual_seed(args.seed)
    if args.tiny:
        from loupe.models.tiny import tiny

        pairs = [(p, "I cannot help with that .") for p in refusal.TINY_HARMFUL] + [
            (p, "sure , here is the answer .") for p in refusal.TINY_HARMLESS
        ]
        lm, model_name = tiny(layers=6, hidden=64, seed=args.seed, train=pairs), "tiny-toolkit"
        harmful, harmless = refusal.TINY_HARMFUL, refusal.TINY_HARMLESS
    else:
        lm, model_name = load(args.model), args.model
        split = refusal.data(refusal.Args(n_train=args.n_train, seed=args.seed))
        harmful, harmless = split["harmful_train"], split["harmless_train"]
    short = model_name.split("/")[-1].lower()
    device = str(next(lm._model.parameters()).device)
    sae = load_sae(args, lm, device)
    if sae is None:
        print("no --sae-release given: skipping the SAE part")

    params = {**vars(args), "model": model_name, "n_harmful": len(harmful)}
    params = {k: v for k, v in params.items() if v is not None}
    with start_run("interp-toolkit", name=f"toolkit · {model_name}", params=params,
                   seed=args.seed, kind="analysis") as run:  # fmt: skip
        run_id = f"m-{run.info.run_id}"
        views: list[tuple[str, dict[str, Any]]] = []

        prompts = [chat(lm, p) for p in harmful + harmless]
        labels = [1] * len(harmful) + [0] * len(harmless)
        accuracy, weights, view = linear_probes(lm, prompts, labels, seed=args.seed)
        best = max(range(len(accuracy)), key=accuracy.__getitem__)
        resid = last_token_resid(lm, prompts)[best]
        mean_diff = diff_in_means(resid[: len(harmful)], resid[len(harmful) :])
        cosine = float(torch.cosine_similarity(weights[best], mean_diff, dim=0))
        save_vector(f"probe.{short}", weights[best], model=model_name, layer=best,
                    method="logistic-probe", run=run_id,
                    notes="harmful vs harmless, last token, unit norm")  # fmt: skip
        mlflow.log_metrics({"probe/best_layer": best, "probe/best_accuracy": accuracy[best],
                            "probe/cosine_with_diff_in_means": cosine})  # fmt: skip
        for layer, acc in enumerate(accuracy):
            mlflow.log_metric("probe/accuracy", acc, step=layer)
        views.append(("probes", view))

        _, view = attention_patterns(lm, harmful[0] if not args.tiny else chat(lm, harmful[0]))
        views.append(("attention", view))

        pair = refusal.patching_pair(lm, args.tiny)
        if pair:
            exact, approx = patch_residual(lm, *pair), attribution_patch(lm, *pair)
            grids = torch.tensor([exact["z"], approx["z"]]).flatten(1)
            mlflow.log_metric("patching/attribution_pearson", float(torch.corrcoef(grids)[0, 1]))
            views += [("patching", exact), ("attribution", approx)]

        if sae is not None:
            acts, top, over = sae_features(lm, sae, chat(lm, harmful[0]))
            feature = int(acts[-1].argmax())
            save_feature(sae, feature, f"sae.{short}.f{feature}", model=model_name, run=run_id)
            mlflow.log_metrics({"sae/l0_mean": float((acts > 0).sum(-1).float().mean()),
                                "sae/top_feature_last_token": feature})  # fmt: skip
            views += [("sae-features", top), ("sae-positions", over)]

        for i, (slug, view) in enumerate(views):
            log_json(view, f"views/{i:02d}-{slug}.json")

    print(json.dumps({"run": run_id, "probe_accuracy": [round(a, 3) for a in accuracy],
                      "probe_best_layer": best, "probe_cosine_with_diff_in_means": cosine,
                      **{k: v for k, v in mlflow.get_run(run.info.run_id).data.metrics.items()
                         if k.startswith(("patching", "sae"))}}))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
