"""Direct preference optimisation with LoRA on pairs of replies to one prompt.

A row is {"prompt": [messages], "chosen": reply, "rejected": reply}: the prompt as chat messages,
the two replies as assistant text. The reference model is the base with the adapter disabled.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from louped.train.base import TrainConfig, fit, read_rows
from louped.train.base import load_config as _load_config


class DpoConfig(TrainConfig):
    """A dpo YAML file."""

    beta: float = 0.1


class Preference(BaseModel):
    prompt: list[dict[str, Any]]
    chosen: str
    rejected: str


def load_config(path: Path) -> DpoConfig:
    return _load_config(path, DpoConfig)


class DpoPlan(BaseModel):
    name: str
    base_model: str
    pairs: int
    beta: float


def plan(cfg: DpoConfig) -> DpoPlan:
    """What a run would do, without loading a model."""
    pairs = len(read_rows(cfg, Preference))
    return DpoPlan(name=cfg.name, base_model=cfg.base_model, pairs=pairs, beta=cfg.beta)


def train(cfg: DpoConfig) -> Path:
    """Run DPO; returns the adapter directory."""
    from datasets import Dataset
    from trl.trainer.dpo_config import DPOConfig
    from trl.trainer.dpo_trainer import DPOTrainer

    pairs: list[Preference] = read_rows(cfg, Preference)
    rows = [
        {"prompt": p.prompt, "chosen": [{"role": "assistant", "content": p.chosen}],
         "rejected": [{"role": "assistant", "content": p.rejected}]}
        for p in pairs
    ]  # fmt: skip

    def make(model: Any, tok: Any, peft: Any, args: dict[str, Any]) -> Any:
        return DPOTrainer(model=model, processing_class=tok, peft_config=peft,
                          train_dataset=Dataset.from_list(rows),
                          args=DPOConfig(**args, beta=cfg.beta,
                                         max_length=cfg.max_seq_length))  # fmt: skip

    return fit(cfg, "dpo", len(rows), make)
