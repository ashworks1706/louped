"""Supervised fine-tuning with LoRA on a curated set of Examples (what `loupe data curate` writes).

The loss is on the reply only: TRL renders the chat template and masks the prompt, which is other
people's words and redaction marks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from loupe.data import Example, conversation, read_jsonl
from loupe.train.base import TrainConfig, TrainError, fit
from loupe.train.base import load_config as _load_config


class SftConfig(TrainConfig):
    """An sft YAML file."""


class SftPlan(BaseModel):
    name: str
    base_model: str
    dataset: Path
    output_dir: Path
    examples: int
    with_tool_calls: int
    epochs: float


def load_config(path: Path) -> SftConfig:
    return _load_config(path, SftConfig)


def _examples(cfg: SftConfig) -> list[Example]:
    try:
        examples = read_jsonl(cfg.dataset)
    except FileNotFoundError as exc:
        raise TrainError(f"{exc}: run loupe data export, verify, review, curate") from exc
    if not examples:
        raise TrainError(f"{cfg.dataset} is empty; nothing has been accepted by a reviewer yet")
    return examples


def plan(cfg: SftConfig) -> SftPlan:
    """What a run would do, without loading a model."""
    examples = _examples(cfg)
    return SftPlan(
        name=cfg.name,
        base_model=cfg.base_model,
        dataset=cfg.dataset,
        output_dir=cfg.output_dir,
        examples=len(examples),
        with_tool_calls=sum(1 for e in examples if e.tool_calls),
        epochs=cfg.train.epochs,
    )


def train(cfg: SftConfig) -> Path:
    """Run the fine-tune; returns the adapter directory."""
    from datasets import Dataset
    from trl.trainer.sft_config import SFTConfig
    from trl.trainer.sft_trainer import SFTTrainer

    examples = _examples(cfg)
    rows = [{"prompt": e.messages, "completion": conversation(e)[-1:]} for e in examples]

    def make(model: Any, tok: Any, peft: Any, args: dict[str, Any]) -> Any:
        return SFTTrainer(model=model, processing_class=tok, peft_config=peft,
                          train_dataset=Dataset.from_list(rows),
                          args=SFTConfig(**args, max_length=cfg.max_seq_length))  # fmt: skip

    return fit(cfg, "sft", len(rows), make)
