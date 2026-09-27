"""LoRA SFT end to end on the tiny model, on CPU: the trl backend, MLflow run, merged export."""

from pathlib import Path

import pytest
import yaml

from loupe import stores
from loupe.core import home
from loupe.data import Example, write_jsonl
from loupe.models.tiny import tiny
from loupe.train.sft import TrainError, load_config, plan, train

SYSTEM = {"role": "system", "content": "you are a help"}


def config(tmp_path: Path, **over) -> Path:
    body = {
        "name": "t-sft",
        "base_model": "tiny-base",
        "dataset": "data/t-sft/sft.jsonl",
        "output_dir": "checkpoints/t-sft",
        "max_seq_length": 64,
        "load_in_4bit": True,  # ignored without a GPU
        "backend": "trl",
        "lora": {"r": 4, "alpha": 8, "target_modules": ["q_proj", "v_proj"]},
        "train": {
            "max_steps": 12,
            "per_device_batch_size": 4,
            "gradient_accumulation": 1,
            "learning_rate": 5e-3,
            "logging_steps": 2,
            "seed": 0,
        },
        "export": {"merge_as": "tiny-tuned"},
        **over,
    }
    path = tmp_path / "sft.yaml"
    path.write_text(yaml.safe_dump(body))
    return path


def test_config_rejects_unknown_keys_and_missing_data(tmp_path: Path) -> None:
    with pytest.raises(TrainError, match="extra"):
        load_config(config(tmp_path, epochz=1))
    cfg = load_config(config(tmp_path))
    assert cfg.dataset == home() / "data/t-sft/sft.jsonl"
    with pytest.raises(TrainError, match="loupe data"):
        plan(cfg)


def test_sft_trains_logs_and_exports(tmp_path: Path) -> None:
    lm = tiny(layers=2, hidden=32)
    base = home() / "models" / "tiny-base"
    lm._model.save_pretrained(base)  # pyright: ignore[reportCallIssue]
    lm.tokenizer.save_pretrained(base)
    rows = [
        Example(
            id=str(i),
            messages=[SYSTEM, {"role": "user", "content": f"write a {o}"}],
            reply=f"sure , the {o} is here .",
        )
        for i, o in enumerate(["cake", "song", "poem", "story"] * 2)
    ]
    write_jsonl(home() / "data/t-sft/sft.jsonl", rows)

    cfg = load_config(config(tmp_path))
    assert plan(cfg).examples == 8
    adapter = train(cfg)

    assert (adapter / "adapter_config.json").exists()
    assert (home() / "models" / "tiny-tuned" / "config.json").exists()
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    detail = stores.get_run(run.id)
    assert (run.experiment, run.model) == ("t-sft", "tiny-base")
    loss = [p.value for p in detail.history["loss"]]
    assert len(loss) >= 3 and loss[-1] < loss[0]
    assert detail.tags["loupe.model"] == "tiny-tuned"
