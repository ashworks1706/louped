"""LoRA SFT end to end on the tiny model, on CPU: the trl backend, MLflow run, merged export."""

import json
from pathlib import Path

import pytest
import yaml

from louped import stores
from louped.core import home
from louped.data import Example, write_jsonl
from louped.models.tiny import tiny
from louped.train.sft import TrainError, load_config, plan, train

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
        "export": {"merge_as": "tiny-tuned", "adapter_as": "t-sft"},
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
    with pytest.raises(TrainError, match="louped data"):
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
    assert (home() / "adapters" / "t-sft" / "adapter_config.json").exists()
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    detail = stores.get_run(run.id)
    assert (run.experiment, run.model) == ("t-sft", "tiny-base")
    loss = [p.value for p in detail.history["loss"]]
    assert len(loss) >= 3 and loss[-1] < loss[0]
    assert detail.tags["louped.model"] == "tiny-tuned"


def test_soft_prompt_trains_and_merges_into_new_tokens(tmp_path: Path) -> None:
    from louped.models import chat, load

    save_base()
    rows = [Example(id=str(i), messages=[{"role": "user", "content": "write a cake"}],
                    reply="sure , the cake is here .") for i in range(8)]  # fmt: skip
    write_jsonl(home() / "data/t-sft/sft.jsonl", rows)
    train(load_config(config(tmp_path, soft_prompt=4, export={"merge_as": "tiny-soft"})))

    soft, base = load("tiny-soft"), load("tiny-base")
    prompt = chat(soft, "write a cake")
    assert prompt.startswith("<soft0><soft1><soft2><soft3>")
    ids = soft.tokenizer(prompt, return_tensors="pt")["input_ids"]
    assert ids.shape[1] == base.tokenizer(chat(base, "write a cake"), return_tensors="pt")[
        "input_ids"].shape[1] + 4  # fmt: skip
    emb = soft._model.get_input_embeddings().weight  # pyright: ignore[reportCallIssue]
    assert emb.shape[0] == len(base.tokenizer) + 4 and emb[-4:].abs().sum() > 0


def save_base(name: str = "tiny-base") -> None:
    lm = tiny(layers=2, hidden=32)
    base = home() / "models" / name
    lm._model.save_pretrained(base)  # pyright: ignore[reportCallIssue]
    lm.tokenizer.save_pretrained(base)


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_dpo_trains_on_preference_pairs(tmp_path: Path) -> None:
    from louped.train import dpo

    save_base()
    user = [{"role": "user", "content": "write a poem"}]
    rows = [{"prompt": user, "chosen": "sure , the poem is here .", "rejected": "I cannot"}] * 4
    write_rows(home() / "data/t-dpo.jsonl", rows)
    path = config(tmp_path, name="t-dpo", dataset="data/t-dpo.jsonl", beta=0.2,
                  export={"merge_as": None})  # fmt: skip
    cfg = dpo.load_config(path)
    assert dpo.plan(cfg).pairs == 4
    assert (dpo.train(cfg) / "adapter_config.json").exists()
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    detail = stores.get_run(run.id)
    assert detail.params["recipe"] == "dpo" and "loss" in detail.history


def test_grpo_rewards_come_from_a_plain_check_and_checkpoints_are_kept(tmp_path: Path) -> None:
    from louped.train import grpo
    from louped.train.rewards import as_reward

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
    assert grpo.plan(cfg).prompts == 4
    (cfg.output_dir / "checkpoint-99").mkdir(parents=True)  # a previous run's, removed
    grpo.train(cfg)
    assert sorted(p.name for p in cfg.output_dir.glob("checkpoint-*")) == [
        "checkpoint-1",
        "checkpoint-2",
    ]
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    history = stores.get_run(run.id).history
    assert any(k.startswith("rewards/says") for k in history)

    from louped.analysis import checkpoints, last_token_resid, over_checkpoints
    from louped.models import load

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

    from louped.inspect_ext import as_scorer

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
    from louped.analysis import model_diff

    lm = tiny(layers=2, hidden=32)
    series, view = model_diff(lm, lm, ["write a poem", "tell me a story"], contrast=["hi", "why"])
    assert all(abs(c - 1) < 1e-5 for c in series["residual cosine"] + series["direction cosine"])
    assert all(abs(n) < 1e-6 for n in series["relative norm change"])
    assert view["kind"] == "line" and len(view["x"]) == 2


def test_grpo_config_rejects_groups_that_do_not_fit_and_no_rewards(tmp_path: Path) -> None:
    from louped.train import grpo

    uneven = config(tmp_path, rewards=["checks.py:says"], num_generations=8,
                    train={"per_device_batch_size": 1, "gradient_accumulation": 10})  # fmt: skip
    with pytest.raises(TrainError, match="multiple of num_generations"):
        grpo.load_config(uneven)
    with pytest.raises(TrainError, match="rewards"):
        grpo.load_config(config(tmp_path, rewards=[]))


def test_checks_load_from_a_module_or_a_file_and_fail_clearly(tmp_path: Path) -> None:
    from louped.train.rewards import load_check

    assert load_check("os.path:basename")("a/b") == "b"
    (tmp_path / "c.py").write_text("def one(completion):\n    return 1.0\n")
    assert load_check("c.py:one", tmp_path)("x") == 1.0
    for spec, message in [("nocolon", "file.py:name"), ("gone.py:f", "no file"),
                          ("c.py:two", "no function")]:  # fmt: skip
        with pytest.raises(TrainError, match=message):
            load_check(spec, tmp_path)


ENV = '''
class Counter:
    seen: list = []

    def reset(self, word: str, **_) -> None:
        Counter.seen.append(word)
        self.calls = 0

    def bump(self, n: int) -> str:
        """Count.

        Args:
            n: How much.

        Returns:
            The count.
        """
        self.calls += n
        return str(self.calls)

    def get_reward(self) -> float:
        return 1.0
'''


def test_grpo_trains_in_a_tool_environment_and_logs_rollouts(tmp_path: Path) -> None:
    from trl.chat_template_utils import qwen3_chat_template

    from louped.train import grpo

    lm = tiny(layers=2, hidden=32)
    base = home() / "models" / "tiny-tools"
    lm._model.save_pretrained(base)  # pyright: ignore[reportCallIssue]
    lm.tokenizer.chat_template = qwen3_chat_template
    lm.tokenizer.save_pretrained(base)
    (tmp_path / "env.py").write_text(ENV)
    user = [{"role": "user", "content": "write a poem"}]
    write_rows(home() / "data/t-env.jsonl", [{"prompt": user, "word": "sure"}] * 4)
    path = config(tmp_path, name="t-env", base_model="tiny-tools", dataset="data/t-env.jsonl",
                  environment="env.py:Counter", num_generations=2, max_completion_length=4,
                  export={"merge_as": None},
                  train={"max_steps": 1, "per_device_batch_size": 2, "gradient_accumulation": 1,
                         "logging_steps": 1, "seed": 0})  # fmt: skip
    cfg = grpo.load_config(path)
    assert grpo.plan(cfg).tools == ["bump"]
    grpo.train(cfg)

    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    assert "rewards/Counter/mean" in stores.get_run(run.id).history
    (view,) = [v.view for v in stores.list_views(run.id) or [] if v.path.endswith("rollouts.json")]
    assert view.kind == "table" and view.columns[:2] == ["step", "reward"]
    assert all(row[1] == 1.0 for row in view.rows)


def test_gym_and_math_checks_score_replies() -> None:
    from louped.train.tasks import gym, gym_rows, math_equal

    (row,) = gym_rows("chain_sum", 1, seed=1)
    right = f"so <answer>{row['answer']}</answer>"
    assert gym(right, row["task"], row["entry"]) == 1.0
    assert gym("no tag", row["task"], row["entry"]) == 0.0
    assert [math_equal(r, a) for r, a in [("it is 1/2", "0.5"), ("3,000 apples", "3000"),
                                           ("no idea", "3")]] == [1.0, 1.0, 0.0]  # fmt: skip


def test_soft_prompt_and_masked_diffusion_stay_on_trl(tmp_path: Path) -> None:
    from louped.train.base import backend

    with pytest.raises(TrainError, match="causal"):
        load_config(config(tmp_path, soft_prompt=4, masked_diffusion=True))
    with pytest.raises(TrainError, match="trl backend"):
        backend(load_config(config(tmp_path, soft_prompt=4, backend="unsloth")))
    assert backend(load_config(config(tmp_path, masked_diffusion=True, backend="auto"))) == "trl"


def test_an_edited_copy_of_a_grpo_config_finds_its_files_through_base_dir(tmp_path: Path) -> None:
    from louped.train.base import TrainError
    from louped.train.cli import Command, run

    save_base()
    (tmp_path / "checks.py").write_text("def says(completion: str) -> float:\n    return 1.0\n")
    write_rows(home() / "data/t-copy.jsonl", [{"prompt": [{"role": "user", "content": "hi"}]}])
    path = config(tmp_path, name="t-copy", dataset="data/t-copy.jsonl", rewards=["checks.py:says"],
                  num_generations=2, train={"per_device_batch_size": 2,
                                            "gradient_accumulation": 1})  # fmt: skip
    copy = tmp_path / "elsewhere" / "grpo.yaml"
    copy.parent.mkdir()
    copy.write_text(path.read_text())
    with pytest.raises((TrainError, FileNotFoundError)):
        run(Command("grpo", copy, dry_run=True))
    run(Command("grpo", copy, dry_run=True, base_dir=tmp_path))


def test_a_sweep_trains_every_combination_and_compares_them(tmp_path: Path) -> None:
    from louped.train import hparams, sft

    assert hparams.combinations(["train.learning_rate=1e-3,5e-3", "lora.r=2"]) == [
        {"train.learning_rate": 1e-3, "lora.r": 2},
        {"train.learning_rate": 5e-3, "lora.r": 2},
    ]
    with pytest.raises(TrainError):
        hparams.combinations(["no-equals"])
    save_base()
    rows = [Example(id=str(i), messages=[{"role": "user", "content": f"write a {o}"}],
                    reply=f"the {o} .") for i, o in enumerate(["cake", "song"] * 2)]  # fmt: skip
    write_jsonl(home() / "data/t-sft/sft.jsonl", rows)
    path = config(tmp_path, train={"max_steps": 2, "per_device_batch_size": 2,
                                   "gradient_accumulation": 1, "logging_steps": 1})  # fmt: skip
    summary = hparams.run(sft, path, ["train.learning_rate=1e-3,5e-3"])

    training = [r for r in stores.list_runs() if r.kind == "training"]
    assert sorted(r.name for r in training) == ["sft · t-sft-0", "sft · t-sft-1"]
    assert {stores.get_run(r.id).params["train.learning_rate"] for r in training} == {
        "0.001",
        "0.005",
    }
    assert (home() / "models" / "tiny-tuned-0").exists() and (
        home() / "models" / "tiny-tuned-1"
    ).exists()
    views = {v.path: v.view for v in stores.list_views(summary)}
    curve = views["views/00-loss.json"]
    assert curve.kind == "line" and set(curve.series) == {"train.learning_rate=0.001",
                                                           "train.learning_rate=0.005"}  # fmt: skip
    final = next(v for p, v in views.items() if p.endswith("final.json"))
    assert final.kind == "table" and len(final.rows) == 2 and final.links is not None
    assert str(final.links[0][-1]).startswith("/run/?id=m-")


def test_reft_trains_through_its_worker_and_logs_loss_and_replies(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    from louped.train import reft

    msgs = [{"role": "user", "content": "What is the capital of France?"}]
    write_jsonl(home() / "data/r/train.jsonl", [Example(id="a", messages=msgs, reply="Paris")])
    write_jsonl(home() / "data/r/test.jsonl", [Example(id="b", messages=msgs, reply="Paris")])
    path = tmp_path / "reft.yaml"
    path.write_text(yaml.safe_dump({"name": "r", "base_model": "tiny-base", "layers": [1, 2],
                                    "dataset": "data/r/train.jsonl", "test": "data/r/test.jsonl",
                                    "output_dir": "checkpoints/r"}))  # fmt: skip
    cfg = reft.load_config(path)
    assert reft.plan(cfg).examples == 1 and cfg.output_dir == home() / "checkpoints/r"
    with pytest.raises(TrainError):
        reft.load_config(tmp_path / "absent.yaml")
    # a stand-in for the pyreft worker: the same files, written the same way
    worker = tmp_path / "worker.py"
    worker.write_text(
        "import json, sys, pathlib\n"
        "job = json.loads(pathlib.Path(sys.argv[1]).read_text())\n"
        "out = pathlib.Path(job['out'])\n"
        "assert job['layers'] == [1, 2] and job['train'][0]['reply'] == 'Paris'\n"
        "with (out / 'metrics.jsonl').open('a') as m:\n"
        "    for s, loss in [(5, 2.0), (10, 0.5)]:\n"
        "        m.write(json.dumps({'step': s, 'loss': loss}) + '\\n')\n"
        "(out / 'replies.json').write_text(json.dumps([{'prompt': 'q', 'target': 'Paris',"
        " 'base': 'The capital of France is Paris.', 'reft': 'Paris'}]))\n"
    )
    monkeypatch.setattr(reft, "command", lambda job: [sys.executable, str(worker), str(job)])
    reft.train(cfg)
    (run,) = [r for r in stores.list_runs() if r.kind == "training"]
    detail = stores.get_run(run.id)
    assert [p.value for p in detail.history["loss"]] == [2.0, 0.5]
    assert detail.metrics["test/reft_words"] == 1 and detail.metrics["test/base_words"] == 6
    assert detail.metrics["test/reft_contains_target"] == 1.0
    (view,) = stores.list_views(run.id)
    assert view.view.kind == "table" and view.view.rows[0][-1] == "Paris"
    monkeypatch.setattr(reft, "command", lambda job: [sys.executable, "-c", "raise SystemExit(3)"])
    with pytest.raises(TrainError, match="exit code 3"):
        reft.train(cfg)


def test_a_replay_environment_serves_recorded_tool_outputs_offline(tmp_path: Path) -> None:
    from transformers.utils.chat_template_utils import get_json_schema

    from louped.train.replay import NO_RECORDING, recordings, replay_environment

    spec = {
        "tools": [{"name": "search", "description": "Search the web.",
                   "parameters": {"properties": {"query": {"type": "string",
                                                           "description": "What to look for."},
                                                 "limit": {"type": "integer",
                                                           "description": "How many."}},
                                  "required": ["query"]}}],
        "calls": [{"tool": "search", "arguments": {"query": "library hours"},
                   "output": "Opens at 10 on Sunday."}],
    }  # fmt: skip
    path = tmp_path / "recordings.json"
    path.write_text(json.dumps(spec))
    Replay = replay_environment(path)
    env = Replay()
    env.reset(expect_tool="search", expect_args="library")
    assert env.search(query="library hours") == "Opens at 10 on Sunday."
    assert env.search(query="gym") == NO_RECORDING
    assert env.get_reward() == 1.0
    env.reset(expect_tool="search", expect_args="library")
    env.search(query="gym")
    assert env.get_reward() == 0.0
    schema = get_json_schema(env.search)["function"]
    assert schema["name"] == "search" and schema["parameters"]["required"] == ["query"]
    assert schema["parameters"]["properties"]["limit"]["type"] == "integer"

    logged = Example(id="a", reply="Opens at 10.", messages=[
        {"role": "user", "content": "when does the library open"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "search", "arguments": '{"query": "library hours"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Opens at 10 on Sunday."},
    ])  # fmt: skip
    assert recordings([logged]) == spec["calls"]
