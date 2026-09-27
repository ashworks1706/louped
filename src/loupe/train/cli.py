"""`loupe train <recipe> <config>`: post-training recipes from a YAML config."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tyro


@dataclass(frozen=True)
class Command:
    """Post-training recipes, each logged as an MLflow training run. sft: LoRA SFT on a curated
    set. dpo: preference pairs. grpo: prompts and reward functions."""

    recipe: tyro.conf.Positional[Literal["sft", "dpo", "grpo"]]
    config: tyro.conf.Positional[Path]
    dry_run: bool = False
    """Print what would run, without loading a model."""


def run(cmd: Command) -> None:
    recipe = importlib.import_module(f"loupe.train.{cmd.recipe}")
    cfg = recipe.load_config(cmd.config)
    shown = recipe.plan(cfg)
    print(shown.model_dump_json(indent=2) if hasattr(shown, "model_dump_json")
          else json.dumps(shown, indent=2, default=str))  # fmt: skip
    if not cmd.dry_run:
        recipe.train(cfg)
