"""`loupe train <recipe> <config>`: post-training recipes from a YAML config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tyro


@dataclass(frozen=True)
class Command:
    """Post-training recipes. sft: LoRA SFT on a curated set, logged as an MLflow training run."""

    recipe: tyro.conf.Positional[Literal["sft"]]
    config: tyro.conf.Positional[Path]
    dry_run: bool = False
    """Print what would run, without loading a model."""


def run(cmd: Command) -> None:
    from loupe.train.sft import load_config, plan, train

    cfg = load_config(cmd.config)
    print(plan(cfg).model_dump_json(indent=2))
    if not cmd.dry_run:
        train(cfg)
