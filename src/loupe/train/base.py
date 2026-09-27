"""What every post-training recipe shares: the config, the backend, loading, the MLflow run, the
adapter and the export. A recipe adds its dataset and its TRL trainer.

Two backends, one config. `unsloth` (4-bit QLoRA, GGUF export) needs a CUDA GPU and the unsloth
package; `trl` is TRL and PEFT on whatever torch has, CPU included. `auto` picks unsloth when both
are there. Relative paths in the config are under LOUPE_HOME, so a config works on any machine.

The run is an MLflow run of kind training: loss and rewards by step show on its Overview, the
config in its Config tab. With `train.save_steps`, adapters are kept at checkpoint-<step> for
analyses across training. With `export.merge_as`, the merged model is saved under <home>/models so
the loupe/ Inspect provider and the Playground can load it by name.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from loupe.core import home, saved_model


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
    #: Keep the adapter every this many steps, as <output_dir>/checkpoint-<step>.
    save_steps: int | None = None
    seed: int = 3407


class Export(_Strict):
    #: Save the merged model as <home>/models/<merge_as>.
    merge_as: str | None = None
    #: llama.cpp quantisation for a GGUF file; unsloth backend only.
    gguf_quant: str | None = None


class TrainConfig(_Strict):
    """The keys every recipe's YAML file has. An unknown or missing key fails."""

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


def _under_home(path: Path) -> Path:
    return path if path.is_absolute() else home() / path


def load_config[C: TrainConfig](path: Path, cls: type[C]) -> C:
    if not path.exists():
        raise TrainError(f"no config at {path}")
    try:
        cfg = cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        raise TrainError(f"{path}: {exc}") from exc
    return cfg.model_copy(
        update={"dataset": _under_home(cfg.dataset), "output_dir": _under_home(cfg.output_dir)}
    )


def read_rows(cfg: TrainConfig, row: type[BaseModel]) -> list[Any]:
    """The dataset's JSONL rows, validated one by one."""
    if not cfg.dataset.exists():
        raise TrainError(f"no dataset at {cfg.dataset}")
    lines = cfg.dataset.read_text(encoding="utf-8").splitlines()
    try:
        rows = [row.model_validate_json(line) for line in lines if line.strip()]
    except ValidationError as exc:
        raise TrainError(f"{cfg.dataset}: {exc}") from exc
    if not rows:
        raise TrainError(f"{cfg.dataset} is empty")
    return rows


def backend(cfg: TrainConfig) -> str:
    if cfg.backend != "auto":
        return cfg.backend
    import torch

    has_unsloth = importlib.util.find_spec("unsloth") is not None
    return "unsloth" if has_unsloth and torch.cuda.is_available() else "trl"


def model_path(name: str) -> str:
    return str(saved_model(name) or name)


def _load(cfg: TrainConfig, kind: str):
    if kind == "unsloth":
        from unsloth import FastLanguageModel  # pyright: ignore[reportMissingImports]

        model, tok = FastLanguageModel.from_pretrained(
            model_name=model_path(cfg.base_model),
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

    path = model_path(cfg.base_model)
    quant = None
    if cfg.load_in_4bit and torch.cuda.is_available():
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(path, quantization_config=quant, dtype="auto")
    tok = tokenizer(path)
    peft = LoraConfig(
        r=cfg.lora.r,
        lora_alpha=cfg.lora.alpha,
        lora_dropout=cfg.lora.dropout,
        target_modules=cfg.lora.target_modules,
        task_type="CAUSAL_LM",
    )
    return model, tok, peft


def tokenizer(path: str):
    from transformers import AutoTokenizer, PreTrainedTokenizerFast

    if Path(path, "tokenizer.json").exists():  # exactly what was saved; see loupe.models.load
        return PreTrainedTokenizerFast.from_pretrained(path)
    return AutoTokenizer.from_pretrained(path)


def trainer_args(cfg: TrainConfig) -> dict[str, Any]:
    """The TRL config keys every recipe sets the same way."""
    import torch

    s = cfg.train
    gpu = torch.cuda.is_available()
    return {
        "output_dir": str(cfg.output_dir),
        "num_train_epochs": s.epochs,
        "max_steps": s.max_steps,
        "per_device_train_batch_size": s.per_device_batch_size,
        "gradient_accumulation_steps": s.gradient_accumulation,
        "learning_rate": s.learning_rate,
        "warmup_steps": s.warmup_ratio,  # transformers 5: a float below 1 is a ratio
        "logging_steps": s.logging_steps,
        "seed": s.seed,
        "report_to": "mlflow",
        "save_strategy": "steps" if s.save_steps else "no",
        "save_steps": s.save_steps or 500,
        "save_only_model": True,
        "bf16": gpu and torch.cuda.is_bf16_supported(),
        "use_cpu": not gpu,
    }


#: Builds a recipe's TRL trainer from the model, tokenizer, PEFT config (None under unsloth) and
#: the shared trainer args.
MakeTrainer = Callable[[Any, Any, Any, dict[str, Any]], Any]


def fit(cfg: TrainConfig, recipe: str, rows: int, make: MakeTrainer) -> Path:
    """Run a recipe's trainer inside an MLflow training run; returns the adapter directory."""
    from loupe.tracking import start_run

    kind = backend(cfg)
    params = {"recipe": recipe, "model": cfg.base_model, "backend": kind, "examples": rows,
              **cfg.model_dump(mode="json")}  # fmt: skip
    with start_run(cfg.experiment or cfg.name, name=f"{recipe} · {cfg.name}", params=_flat(params),
                   seed=cfg.train.seed, kind="training") as run:  # fmt: skip
        model, tok, peft = _load(cfg, kind)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        trainer = make(model, tok, peft, trainer_args(cfg))
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


def _export(cfg: TrainConfig, kind: str, model, tok) -> None:
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
