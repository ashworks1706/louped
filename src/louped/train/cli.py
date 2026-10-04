"""`louped train <recipe> <config>`: post-training recipes from a YAML config."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tyro


@dataclass(frozen=True)
class Command:
    """Post-training recipes, each logged as an MLflow training run. sft: LoRA SFT on a curated
    set. dpo: preference pairs. grpo: prompts and reward functions. classify: a small text
    classifier on a sentence encoder. reft: a low-rank representation intervention (pyreft, in
    its own environment through uv)."""

    recipe: tyro.conf.Positional[Literal["sft", "dpo", "grpo", "classify", "reft"]]
    config: tyro.conf.Positional[Path]
    dry_run: bool = False
    """Print what would run, without loading a model."""
    base_dir: Path | None = None
    """Where files the config names by a relative path (rewards, environment) are; by default
    the config's own folder. For an edited copy of a config kept elsewhere."""
    sweep: tuple[str, ...] = ()
    """key=value,value over the config, e.g. train.learning_rate=1e-4,2e-4 lora.r=8,16: every
    combination is its own run, compared in one summary run."""


def run(cmd: Command) -> None:
    recipe = importlib.import_module(f"louped.train.{cmd.recipe}")
    if cmd.sweep:
        from louped.train import hparams

        combos = hparams.combinations(list(cmd.sweep))
        print(f"{len(combos)} runs:", *combos, sep="\n  ")
        if not cmd.dry_run:
            print(hparams.run(recipe, cmd.config, list(cmd.sweep), cmd.base_dir))
        return
    cfg = recipe.load_config(cmd.config)
    if cmd.base_dir is not None and hasattr(cfg, "_base_dir"):
        cfg._base_dir = cmd.base_dir
    print(recipe.plan(cfg).model_dump_json(indent=2))
    if not cmd.dry_run:
        recipe.train(cfg)
