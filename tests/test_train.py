"""LoRA SFT end to end on the tiny model, on CPU: the trl backend, MLflow run, merged export."""

import json
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


def save_base(name: str = "tiny-base") -> None:
    lm = tiny(layers=2, hidden=32)
    base = home() / "models" / name
    lm._model.save_pretrained(base)  # pyright: ignore[reportCallIssue]
    lm.tokenizer.save_pretrained(base)


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_dpo_trains_on_preference_pairs(tmp_path: Path) -> None:
    from loupe.train import dpo

    save_base()
    user = [{"role": "user", "content": "write a poem"}]
    rows = [{"prompt": user, "chosen": "sure , the poem is here .", "rejected": "I cannot"}] * 4
    write_rows(home() / "data/t-dpo.jsonl", rows)
    path = config(tmp_path, name="t-dpo", dataset="data/t-dpo.jsonl", beta=0.2,
                  export={"merge_as": None})  # fmt: skip
    cfg = dpo.load_config(path)
    assert dpo.plan(cfg)["pairs"] == 4
    assert (dpo.train(cfg) / "adapter_config.json").exists()
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    detail = stores.get_run(run.id)
    assert detail.params["recipe"] == "dpo" and "loss" in detail.history


def test_grpo_rewards_come_from_a_plain_check_and_checkpoints_are_kept(tmp_path: Path) -> None:
    from loupe.train import grpo
    from loupe.train.rewards import as_reward

    save_base()
    (tmp_path / "checks.py").write_text(
        "def says(completion: str, word: str) -> float:\n    return float(word in completion)\n"
    )
    user = [{"role": "user", "content": "write a poem"}]
    write_rows(home() / "data/t-grpo.jsonl", [{"prompt": user, "word": "sure"}] * 4)
    path = config(tmp_path, name="t-grpo", dataset="data/t-grpo.jsonl", rewards=["checks.py:says"],
                  num_generations=2, max_completion_length=4, export={"merge_as": None},
                  train={"max_steps": 2, "per_device_batch_size": 2, "gradient_accumulation": 1,
                         "logging_steps": 1, "save_steps": 1, "seed": 0})  # fmt: skip
    cfg = grpo.load_config(path)
    assert grpo.plan(cfg)["prompts"] == 4
    grpo.train(cfg)
    assert sorted(p.name for p in cfg.output_dir.glob("checkpoint-*")) == [
        "checkpoint-1",
        "checkpoint-2",
    ]
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    history = stores.get_run(run.id).history
    assert any(k.startswith("rewards/says") for k in history)

    from loupe.analysis import checkpoints, last_token_resid, over_checkpoints
    from loupe.models import load

    def norm(lm) -> float:
        return float(last_token_resid(lm, ["write a poem"]).norm())

    kept = checkpoints(cfg.output_dir)
    assert [step for step, _ in kept] == [1, 2]
    series, view = over_checkpoints("tiny-base", kept, {"norm": norm})
    assert view["x"] == [0.0, 1.0, 2.0] and series["norm"][0] == norm(load("tiny-base"))

    def exact(completion: str, target: str) -> float:
        return float(completion == target)

    reward = as_reward(exact)
    assert reward([], ["a", [{"role": "assistant", "content": "b"}]], target=["a", "c"],
                  extra=[1, 2]) == [1.0, 0.0]  # fmt: skip


def test_the_same_check_scores_an_inspect_eval() -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ModelOutput, get_model
    from inspect_ai.solver import generate

    from loupe.inspect_ext import as_scorer

    def says(completion: str, word: str) -> float:
        return float(word in completion)

    outputs = [ModelOutput.from_content("mockllm/model", a) for a in ["sure thing", "no"]]
    samples = [Sample(input="q", metadata={"word": "sure"}) for _ in range(2)]
    model = get_model("mockllm/model", custom_outputs=outputs)
    task = Task(dataset=samples, solver=generate(), scorer=as_scorer(says))
    [log] = eval(task, model=model, display="none")
    assert log.results is not None
    assert log.results.scores[0].name == "says"
    assert log.results.scores[0].metrics["mean"].value == 0.5


def test_a_model_diffed_with_itself_is_unchanged() -> None:
    from loupe.analysis import model_diff

    lm = tiny(layers=2, hidden=32)
    series, view = model_diff(lm, lm, ["write a poem", "tell me a story"], contrast=["hi", "why"])
    assert all(abs(c - 1) < 1e-5 for c in series["residual cosine"] + series["direction cosine"])
    assert all(abs(n) < 1e-6 for n in series["relative norm change"])
    assert view["kind"] == "line" and len(view["x"]) == 2
