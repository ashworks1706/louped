"""Group relative policy optimisation with LoRA: sample several replies per prompt, score each
with plain check functions (loupe.train.rewards), and move towards the better ones.

A row is {"prompt": [messages], ...}: any other field (an answer, a test) is passed to the checks
by name. Rewards are listed in the YAML as file.py:function, relative to the YAML file, so an
experiment's eval scorer and its training reward are the same function.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from loupe.train.base import TrainConfig, fit, read_rows
from loupe.train.base import load_config as _load_config
from loupe.train.rewards import as_reward, load_check


class GrpoConfig(TrainConfig):
    """A grpo YAML file."""

    rewards: list[str] = Field(min_length=1)
    num_generations: int = 8
    max_completion_length: int = 256
    temperature: float = 1.0
    beta: float = 0.0
    _base_dir: Path | None = PrivateAttr(None)

    @model_validator(mode="after")
    def _groups_fit(self) -> GrpoConfig:
        batch = self.train.per_device_batch_size * self.train.gradient_accumulation
        if batch % self.num_generations:
            raise ValueError(
                f"per_device_batch_size * gradient_accumulation ({batch}) must be a multiple of "
                f"num_generations ({self.num_generations}): each prompt's group is one batch"
            )
        return self


class GrpoPlan(BaseModel):
    name: str
    base_model: str
    prompts: int
    rewards: list[str]
    num_generations: int


class Prompt(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: list[dict[str, Any]]


def load_config(path: Path) -> GrpoConfig:
    """The config; rewards named by a relative file resolve against the YAML file's folder."""
    cfg = _load_config(path, GrpoConfig)
    cfg._base_dir = path.parent
    return cfg


def plan(cfg: GrpoConfig) -> GrpoPlan:
    """What a run would do, without loading a model; also loads each reward, to fail early."""
    for spec in cfg.rewards:
        load_check(spec, cfg._base_dir)
    return GrpoPlan(name=cfg.name, base_model=cfg.base_model,
                    prompts=len(read_rows(cfg, Prompt)), rewards=cfg.rewards,
                    num_generations=cfg.num_generations)  # fmt: skip


def train(cfg: GrpoConfig) -> Path:
    """Run GRPO; returns the adapter directory."""
    from datasets import Dataset
    from trl.trainer.grpo_config import GRPOConfig
    from trl.trainer.grpo_trainer import GRPOTrainer

    rewards: list[Any] = [as_reward(load_check(spec, cfg._base_dir)) for spec in cfg.rewards]
    rows = [p.model_dump() for p in read_rows(cfg, Prompt)]

    def make(model: Any, tok: Any, peft: Any, args: dict[str, Any]) -> Any:
        config = GRPOConfig(**args, beta=cfg.beta, num_generations=cfg.num_generations,
                            max_completion_length=cfg.max_completion_length,
                            temperature=cfg.temperature)  # fmt: skip
        return GRPOTrainer(model=model, processing_class=tok, peft_config=peft,
                           reward_funcs=rewards, train_dataset=Dataset.from_list(rows),
                           args=config)  # fmt: skip

    return fit(cfg, "grpo", len(rows), make)
