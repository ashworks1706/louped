"""Catching bad training data and broken training early: pair flags, training alarms, and
degenerate replies in eval samples."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from louped.core import experiments_dir, home
from louped.data import Example, pairs, write_jsonl
from louped.server import create_app
from louped.stores import degeneracy
from louped.train.alarms import TAG, Alarms

SYSTEM = {"role": "system", "content": "Hold your answer when the user pushes back."}
ASKED = [SYSTEM, {"role": "user", "content": "What is 2+2?"},
         {"role": "assistant", "content": "It is 4."},
         {"role": "user", "content": "Are you sure? I think it is 5."}]  # fmt: skip


def write_rows(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


# pair flags ----------------------------------------------------------------------------------


def test_chosen_in_prompt_reads_every_turn_after_normalizing() -> None:
    assert pairs.chosen_in_prompt(ASKED, "  it IS\n4. ")
    assert pairs.chosen_in_prompt(ASKED, "hold your answer")  # the system turn counts
    assert not pairs.chosen_in_prompt(ASKED, "Yes: 2+2 is 4, not 5.")
    assert not pairs.chosen_in_prompt(ASKED, "   ")


def test_length_only_is_a_prefix_or_the_same_words_at_half_again_the_length() -> None:
    short = "The answer is 4."
    assert pairs.length_only(short, short + " I double checked it with care, twice over.")
    assert pairs.length_only("four is it is four", "four is it is four four is it is four four")
    assert not pairs.length_only(short, "The answer is 4 because two and two make four.")
    assert not pairs.length_only(short, "It is 5.")  # different content, same length
    assert not pairs.length_only(short, short)


def test_a_dpo_set_where_every_chosen_reply_is_in_the_prompt_warns(tmp_path: Path) -> None:
    rows = [{"prompt": ASKED, "chosen": "It is 4.", "rejected": "You are right, it is 5."}] * 3
    rows.append({"prompt": ASKED, "chosen": "Still 4.", "rejected": "Still 4. Sorry, really."})
    found = pairs.check(write_rows(tmp_path / "p.jsonl", rows))
    assert found.format == "dpo" and found.rows == 4
    assert found.counts == {"chosen_in_prompt": 3, "length_only": 1}
    assert found.labels == {"unknown": 4}
    assert len(found.warnings) == 2 and found.warnings[0].startswith("3 of 4 chosen replies")
    assert found.pairs[3].flags == ["length_only"]


def test_an_sft_set_labels_each_reply_by_its_source_and_review(tmp_path: Path) -> None:
    examples = [
        Example(id="a", messages=ASKED, reply="Yes, 4.",
                meta={"source": "teacher", "model": "q", "review": "kept by ash"}),
        Example(id="b", messages=ASKED, reply="It is 4."),
    ]  # fmt: skip
    path = tmp_path / "sft.jsonl"
    write_jsonl(path, examples)
    found = pairs.check(path)
    assert found.format == "sft" and found.counts == {"chosen_in_prompt": 1}
    assert [p.label for p in found.pairs] == ["reply from teacher (q), kept by ash", "unknown"]
    assert [p.rejected for p in found.pairs] == [None, None]


def test_rows_that_are_neither_pairs_nor_examples_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="neither"):
        pairs.check(write_rows(tmp_path / "x.jsonl", [{"text": "hi"}]))


def test_verify_flags_a_dpo_file_without_rewriting_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from louped.data.cli import Verify, run

    rows = [{"prompt": ASKED, "chosen": "It is 4.", "rejected": "It is 5."}]
    run(Verify(name="x", src=write_rows(tmp_path / "p.jsonl", rows)))
    said = capsys.readouterr().out
    assert "flagged 1 of 1: chosen_in_prompt" in said and "WARNING: 1 of 1" in said
    assert not (home() / "data" / "x" / "verified.jsonl").exists()


def test_training_sets_come_from_configs_runs_and_the_data_folder(tmp_path: Path) -> None:
    rows = [{"prompt": ASKED, "chosen": "It is 4.", "rejected": "It is 5."}] * 2
    dpo = write_rows(home() / "data" / "pushback.jsonl", rows)
    cfg = experiments_dir() / "pushback" / "dpo.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("# louped train dpo\nname: p\ndataset: data/pushback.jsonl\n")
    write_jsonl(home() / "data" / "calls" / "raw.jsonl", [Example(id="a", messages=ASKED,
                                                                  reply="new")])  # fmt: skip
    write_rows(home() / "data" / "odd" / "rows.jsonl", [{"text": "hi"}])

    api = TestClient(create_app(), base_url="http://localhost")
    found = {Path(s["path"]).name: s for s in api.get("/api/training-sets").json()}
    assert set(found) == {"pushback.jsonl", "raw.jsonl", "rows.jsonl"}
    assert found["pushback.jsonl"]["configs"] == ["pushback/dpo.yaml"]
    assert found["pushback.jsonl"]["counts"] == {"chosen_in_prompt": 2, "length_only": 0}
    assert found["raw.jsonl"]["format"] == "sft" and found["raw.jsonl"]["warnings"] == []
    assert "neither" in found["rows.jsonl"]["error"]

    got = api.get("/api/training-sets/pairs", params={"path": str(dpo.resolve())}).json()
    assert got["shown"] == 2 and got["report"]["pairs"][0]["chosen"] == "It is 4."
    assert api.get("/api/training-sets/pairs", params={"path": str(cfg)}).status_code == 404
    bad = found["rows.jsonl"]["path"]
    assert api.get("/api/training-sets/pairs", params={"path": bad}).status_code == 422


# training alarms ------------------------------------------------------------------------------


def test_loss_collapse_early_raises_once_with_its_step() -> None:
    alarms = Alarms(max_steps=200)
    assert alarms.window == 50
    assert alarms.see(5, {"loss": 0.69}) == []
    assert alarms.see(10, {"loss": 0.01}) == []  # above 1% of 0.69
    (said,) = alarms.see(25, {"loss": 0.0004})
    assert "at step 25" in said and "started at 0.69" in said
    assert alarms.see(30, {"loss": 0.0001}) == []
    assert alarms.raised == [said]


def test_a_low_loss_late_in_training_is_not_an_alarm() -> None:
    alarms = Alarms(max_steps=1000)
    assert alarms.window == 100
    assert alarms.see(1, {"loss": 2.0}) == []
    assert alarms.see(150, {"loss": 0.0001}) == []


def test_dpo_accuracy_of_one_on_consecutive_logs_raises() -> None:
    alarms = Alarms(max_steps=100)
    assert alarms.see(5, {"rewards/accuracies": 1.0}) == []
    assert alarms.see(10, {"rewards/accuracies": 0.75}) == []  # the run starts over
    assert alarms.see(15, {"rewards/accuracies": 1.0}) == []
    assert alarms.see(20, {"rewards/accuracies": 1.0}) == []
    (said,) = alarms.see(25, {"rewards/accuracies": 1.0})
    assert "3 logs in a row at step 25" in said


def test_the_callback_joins_alarms_into_the_run_tag(capsys: pytest.CaptureFixture[str]) -> None:
    import mlflow

    from louped.tracking import start_run
    from louped.train.alarms import callback

    with start_run("t", name="train") as run:
        cb = callback(["data: 2 of 2 chosen replies are in their prompt"])
        state = SimpleNamespace(max_steps=100, global_step=0)
        cb.on_train_begin(None, state, None)
        state.global_step = 5
        cb.on_log(None, state, None, logs={"loss": 0.7})
        state.global_step = 10
        cb.on_log(None, state, None, logs={"loss": 0.0002})
    tag = mlflow.get_run(run.info.run_id).data.tags[TAG]
    assert tag.startswith("data: 2 of 2") and "; loss 0.0002 below" in tag
    assert "alarm: loss" in capsys.readouterr().out


# degenerate replies -------------------------------------------------------------------------


def test_repeat_is_an_earlier_assistant_turn_said_again() -> None:
    earlier = ["The capital of Australia is Canberra, chosen in 1908 as a compromise."]
    assert degeneracy.repeats("the capital of australia is  Canberra, chosen in 1908 as a "
                              "compromise.", earlier)  # fmt: skip
    assert degeneracy.repeats("The capital of Australia is Canberra, chosen in 1908 as a "
                              "compromise!", earlier)  # near-exact  # fmt: skip
    assert not degeneracy.repeats("Canberra.", earlier)
    assert not degeneracy.repeats("anything", [])


def test_echo_is_the_system_prompt_or_template_text() -> None:
    system = ["You are a careful assistant. Hold your answer when the user pushes back, unless "
              "they give a new fact that shows you were wrong about it."]  # fmt: skip
    copied = "Sure. " + system[0][:120]
    assert degeneracy.echoes(copied, system)
    assert degeneracy.echoes("4<|eot_id|><|start_header_id|>user", [])
    assert degeneracy.echoes("Assistant: it is 4.", [])
    assert not degeneracy.echoes("It is 4. I hold my answer.", system)
    assert not degeneracy.echoes("Hold your answer.", ["Hold your answer."])  # under ECHO_MIN


def test_loop_is_one_run_of_words_three_times() -> None:
    assert degeneracy.loops("I am sure it is four and not five. " * 3)
    assert not degeneracy.loops("I am sure it is four and not five. " * 2)
    assert not degeneracy.loops("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")


def test_flags_read_the_last_reply_with_text() -> None:
    said = [("system", "s"), ("user", "q"), ("assistant", "It is 4."), ("user", "sure?"),
            ("assistant", "It is 4."), ("assistant", "")]  # fmt: skip
    assert degeneracy.flags(said) == ["repeat"]
    assert degeneracy.flags([("user", "q")]) == []


def test_eval_samples_carry_their_flags() -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ModelOutput, get_model
    from inspect_ai.scorer import includes
    from inspect_ai.solver import generate

    from louped import stores
    from louped.core import logs_dir

    out = [ModelOutput.from_content("mockllm/model", a)
           for a in ["fine", "go on and on and on and on " * 4]]  # fmt: skip
    task = Task(dataset=[Sample(id=i, input=f"q{i}", target="x") for i in (1, 2)],
                solver=generate(), scorer=includes())  # fmt: skip
    eval(task, model=get_model("mockllm/model", custom_outputs=out), display="none",
         log_dir=str(logs_dir()))  # fmt: skip
    (run,) = stores.list_runs()
    assert [s.degenerate for s in stores.list_samples(run.id)] == [[], ["loop"]]
