"""Group relative policy optimisation with LoRA: sample several replies per prompt, score each
with plain check functions (loupe.train.rewards), and move towards the better ones.

A row is {"prompt": [messages], ...}: any other field (an answer, a test) is passed to the checks
by name. Rewards are listed in the YAML as file.py:function, relative to the YAML file, so an
experiment's eval scorer and its training reward are the same function.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from loupe.train.base import TrainConfig, TrainError, fit, read_rows
from loupe.train.base import load_config as _load_config
from loupe.train.rewards import as_reward, load_check


class GrpoConfig(TrainConfig):
    """A grpo YAML file."""

    rewards: list[str]
    num_generations: int = 8
    max_completion_length: int = 256
    temperature: float = 1.0
    beta: float = 0.0
    #: Where rewards resolve relative paths; the YAML file's folder when loaded from one.
    base_dir: Path | None = None


class Prompt(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: list[dict[str, Any]]


def load_config(path: Path) -> GrpoConfig:
    cfg = _load_config(path, GrpoConfig)
    return cfg.model_copy(update={"base_dir": cfg.base_dir or path.parent})


def plan(cfg: GrpoConfig) -> dict[str, Any]:
    """What a run would do, without loading a model; also loads each reward, to fail early."""
    for spec in cfg.rewards:
        load_check(spec, cfg.base_dir)
    return {"name": cfg.name, "base_model": cfg.base_model, "prompts": len(read_rows(cfg, Prompt)),
            "rewards": cfg.rewards, "num_generations": cfg.num_generations}  # fmt: skip


def train(cfg: GrpoConfig) -> Path:
    """Run GRPO; returns the adapter directory."""
    from datasets import Dataset
    from trl.trainer.grpo_config import GRPOConfig
    from trl.trainer.grpo_trainer import GRPOTrainer

    if not cfg.rewards:
        raise TrainError("grpo needs at least one reward")
    rewards: list[Any] = [as_reward(load_check(spec, cfg.base_dir)) for spec in cfg.rewards]
    rows = [p.model_dump() for p in read_rows(cfg, Prompt)]

    def make(model: Any, tok: Any, peft: Any, args: dict[str, Any]) -> Any:
        batch = args["per_device_train_batch_size"] * args["gradient_accumulation_steps"]
        config = GRPOConfig(**args, beta=cfg.beta, num_generations=cfg.num_generations,
                            max_completion_length=cfg.max_completion_length,
                            temperature=cfg.temperature,
                            generation_batch_size=max(batch, cfg.num_generations))  # fmt: skip
        return GRPOTrainer(model=model, processing_class=tok, peft_config=peft,
                           reward_funcs=rewards, train_dataset=Dataset.from_list(rows),
                           args=config)  # fmt: skip

    return fit(cfg, "grpo", len(rows), make)
