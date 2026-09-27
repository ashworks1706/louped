"""Supervised fine-tuning with LoRA on a curated set of Examples.

Two backends, one config. `unsloth` (4-bit QLoRA, GGUF export) needs a CUDA GPU and the unsloth
package; `trl` is TRL and PEFT on whatever torch has, CPU included. `auto` picks unsloth when both
are there. Relative paths in the config are under LOUPE_HOME, so a config works on any machine.

The run is an MLflow run of kind training: loss by step shows on its Overview, the config in its
Config tab. With `export.merge_as`, the merged model is saved under <home>/models so the loupe/
Inspect provider and the Playground can load it by name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from loupe.core import home, saved_model
from loupe.data import Example, conversation, read_jsonl


class TrainError(RuntimeError):
    """A config, dataset or backend is missing or wrong."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Lora(_Strict):
    r: int = 16
    alpha: int = 32
    dropout: float = 0.0
    target_modules: list[str] = ["q_proj", "k_proj", "v_proj", "o_proj",
                                 "gate_proj", "up_proj", "down_proj"]  # fmt: skip


class Schedule(_Strict):
    epochs: float = 2
    max_steps: int = -1
    per_device_batch_size: int = 1
    gradient_accumulation: int = 8
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03
    logging_steps: int = 5
    seed: int = 3407


class Export(_Strict):
    #: Save the merged model as <home>/models/<merge_as>.
    merge_as: str | None = None
    #: llama.cpp quantisation for a GGUF file; unsloth backend only.
    gguf_quant: str | None = None


class SftConfig(_Strict):
    """An sft YAML file. An unknown or missing key fails."""

    name: str
    experiment: str | None = None
    base_model: str
    dataset: Path
    output_dir: Path
    max_seq_length: int = 4096
    load_in_4bit: bool = True
    backend: Literal["auto", "unsloth", "trl"] = "auto"
    lora: Lora = Lora()
    train: Schedule = Schedule()
    export: Export = Export()


class SftPlan(BaseModel):
    name: str
    base_model: str
    backend: str
    dataset: Path
    output_dir: Path
    examples: int
    with_tool_calls: int
    epochs: float


def _under_home(path: Path) -> Path:
    return path if path.is_absolute() else home() / path


def load_config(path: Path) -> SftConfig:
    if not path.exists():
        raise TrainError(f"no config at {path}")
    try:
        cfg = SftConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        raise TrainError(f"{path}: {exc}") from exc
    return cfg.model_copy(
        update={"dataset": _under_home(cfg.dataset), "output_dir": _under_home(cfg.output_dir)}
    )


def _examples(cfg: SftConfig) -> list[Example]:
    try:
        examples = read_jsonl(cfg.dataset)
    except FileNotFoundError as exc:
        raise TrainError(f"{exc}: run loupe data export, verify, review, curate") from exc
    if not examples:
        raise TrainError(f"{cfg.dataset} is empty; nothing has been accepted by a reviewer yet")
    return examples


def backend(cfg: SftConfig) -> str:
    if cfg.backend != "auto":
        return cfg.backend
    import torch

    has_unsloth = importlib.util.find_spec("unsloth") is not None
    return "unsloth" if has_unsloth and torch.cuda.is_available() else "trl"


def plan(cfg: SftConfig) -> SftPlan:
    """What a run would do, without loading a model."""
    examples = _examples(cfg)
    return SftPlan(
        name=cfg.name,
        base_model=cfg.base_model,
        backend=backend(cfg),
        dataset=cfg.dataset,
        output_dir=cfg.output_dir,
        examples=len(examples),
        with_tool_calls=sum(1 for e in examples if e.tool_calls),
        epochs=cfg.train.epochs,
    )


def _model_path(name: str) -> str:
    return str(saved_model(name) or name)


def _load(cfg: SftConfig, kind: str):
    if kind == "unsloth":
        from unsloth import FastLanguageModel  # pyright: ignore[reportMissingImports]

        model, tok = FastLanguageModel.from_pretrained(
            model_name=_model_path(cfg.base_model),
            max_seq_length=cfg.max_seq_length,
            load_in_4bit=cfg.load_in_4bit,
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=cfg.lora.r,
            lora_alpha=cfg.lora.alpha,
            lora_dropout=cfg.lora.dropout,
            target_modules=cfg.lora.target_modules,
            random_state=cfg.train.seed,
        )
        return model, tok, None

    import torch
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    path = _model_path(cfg.base_model)
    quant = None
    if cfg.load_in_4bit and torch.cuda.is_available():
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(path, quantization_config=quant, dtype="auto")
    tok = _tokenizer(path)
    peft = LoraConfig(
        r=cfg.lora.r,
        lora_alpha=cfg.lora.alpha,
        lora_dropout=cfg.lora.dropout,
        target_modules=cfg.lora.target_modules,
        task_type="CAUSAL_LM",
    )
    return model, tok, peft


def _tokenizer(path: str):
    from transformers import AutoTokenizer, PreTrainedTokenizerFast

    if Path(path, "tokenizer.json").exists():  # exactly what was saved; see loupe.models.load
        return PreTrainedTokenizerFast.from_pretrained(path)
    return AutoTokenizer.from_pretrained(path)


def train(cfg: SftConfig) -> Path:
    """Run the fine-tune; returns the adapter directory."""
    from datasets import Dataset
    from trl.trainer.sft_config import SFTConfig as TrlConfig
    from trl.trainer.sft_trainer import SFTTrainer

    from loupe.tracking import start_run

    examples = _examples(cfg)
    kind = backend(cfg)
    params = {
        "model": cfg.base_model,
        "backend": kind,
        "examples": len(examples),
        **cfg.model_dump(mode="json"),
    }
    with start_run(cfg.experiment or cfg.name, name=f"sft · {cfg.name}", params=_flat(params),
                   seed=cfg.train.seed, kind="training") as run:  # fmt: skip
        model, tok, peft = _load(cfg, kind)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        # Prompt-completion rows: TRL renders the chat template itself and puts the loss on the
        # reply only, not on the prompts (which are other people's words and redaction marks).
        rows = [{"prompt": e.messages, "completion": conversation(e)[-1:]} for e in examples]
        s = cfg.train
        import torch

        gpu = torch.cuda.is_available()
        trainer = SFTTrainer(
            model=model,
            processing_class=tok,
            peft_config=peft,
            train_dataset=Dataset.from_list(rows),
            args=TrlConfig(
                output_dir=str(cfg.output_dir),
                num_train_epochs=s.epochs,
                max_steps=s.max_steps,
                per_device_train_batch_size=s.per_device_batch_size,
                gradient_accumulation_steps=s.gradient_accumulation,
                learning_rate=s.learning_rate,
                warmup_steps=s.warmup_ratio,  # transformers 5: a float below 1 is a ratio
                logging_steps=s.logging_steps,
                seed=s.seed,
                report_to="mlflow",
                max_length=cfg.max_seq_length,
                save_strategy="no",
                bf16=gpu and torch.cuda.is_bf16_supported(),
                use_cpu=not gpu,
            ),
        )
        trainer.train()
        adapter = cfg.output_dir / "adapter"
        tuned: Any = trainer.model
        tuned.save_pretrained(str(adapter))
        tok.save_pretrained(str(adapter))
        _export(cfg, kind, tuned, tok)
        import mlflow

        mlflow.set_tag("loupe.adapter", str(adapter))
        if cfg.export.merge_as:
            mlflow.set_tag("loupe.model", cfg.export.merge_as)
        print(f"run m-{run.info.run_id}: adapter at {adapter}")
    return adapter


def _export(cfg: SftConfig, kind: str, model, tok) -> None:
    if cfg.export.gguf_quant:
        if kind != "unsloth":
            raise TrainError("gguf export needs the unsloth backend (a CUDA GPU and unsloth)")
        model.save_pretrained_gguf(str(cfg.output_dir / "gguf"), tok,
                                   quantization_method=cfg.export.gguf_quant)  # fmt: skip
    if cfg.export.merge_as:
        target = home() / "models" / cfg.export.merge_as
        merged = model.merge_and_unload()
        merged.save_pretrained(str(target))
        tok.save_pretrained(str(target))


def _flat(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, f"{key}."))
        else:
            out[key] = v
    return out
