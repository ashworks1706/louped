"""Supervised fine-tuning with LoRA on a curated set of Examples (what `loupe data curate` writes).

The loss is on the reply only: TRL renders the chat template and masks the prompt, which is other
people's words and redaction marks. With masked_diffusion, the base is a masked diffusion model
(loupe.models.diffusion) trained on its own objective by a plain transformers Trainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, model_validator

from loupe.data import Example, conversation, read_jsonl
from loupe.train.base import TrainConfig, TrainError, fit
from loupe.train.base import load_config as _load_config


class SftConfig(TrainConfig):
    """An sft YAML file."""

    #: The base is a masked diffusion model (LLaDA, Dream, a masked LM); trl backend only.
    masked_diffusion: bool = False

    @model_validator(mode="after")
    def _one_method(self) -> SftConfig:
        if self.masked_diffusion and self.soft_prompt:
            raise ValueError("soft_prompt is for causal LMs; masked_diffusion trains LoRA")
        return self


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
    if cfg.masked_diffusion:
        return fit(cfg, "sft", len(examples), lambda *a: _diffusion_trainer(cfg, examples, *a))
    rows = [{"prompt": e.messages, "completion": conversation(e)[-1:]} for e in examples]

    def make(model: Any, tok: Any, peft: Any, args: dict[str, Any]) -> Any:
        return SFTTrainer(model=model, processing_class=tok, peft_config=peft,
                          train_dataset=Dataset.from_list(rows),
                          args=SFTConfig(**args, max_length=cfg.max_seq_length))  # fmt: skip

    return fit(cfg, "sft", len(rows), make)


def _diffusion_trainer(
    cfg: SftConfig, examples: list[Example], model: Any, tok: Any, lora: Any, args: dict[str, Any]
) -> Any:
    import torch
    from datasets import Dataset
    from peft import get_peft_model
    from transformers import Trainer, TrainingArguments

    from loupe.models.diffusion import Diffusion, load_mask, loss

    rows = []
    for e in examples:
        prompt = tok.apply_chat_template(e.messages, tokenize=False, add_generation_prompt=True)
        p = tok(str(prompt), add_special_tokens=False)["input_ids"]
        r = tok(e.reply, add_special_tokens=False)["input_ids"] + [tok.eos_token_id]
        rows.append({"ids": (p + r)[: cfg.max_seq_length], "prompt_len": len(p)})
    d = Diffusion(get_peft_model(model, lora), tok, *load_mask(model, tok))

    def collate(batch: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        width = max(len(b["ids"]) for b in batch)  # padded with eos, which the reply learns
        ids = [b["ids"] + [tok.eos_token_id] * (width - len(b["ids"])) for b in batch]
        return {
            "ids": torch.tensor(ids),
            "prompt_len": torch.tensor([b["prompt_len"] for b in batch]),
        }

    class _Trainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            return loss(d, inputs["ids"], inputs["prompt_len"])

    return _Trainer(model=d.model, args=TrainingArguments(**args, remove_unused_columns=False),
                    train_dataset=Dataset.from_list(rows), data_collator=collate)  # fmt: skip
