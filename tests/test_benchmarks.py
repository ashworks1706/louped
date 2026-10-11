"""The Benchmarks pages: eval tasks with their runs as leaderboards, Hub datasets made benchmarks by
a field mapping (the generic Inspect task louped/<name>), and `louped bench` runs by speed. The
Hub and its dataset viewer are stood in for: no test reaches them."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

import pytest
from inspect_ai.dataset import MemoryDataset
from test_agent import call, tools
from test_datasets import GSM8K, Viewer
from test_hub import TOML, client

from louped.core.benchmarks import Benchmark
from louped.inspect_ext import benchmark as generic
from louped.server import datasets

GSM8K_TABLE = """
[benchmarks.gsm8k]
dataset = "openai/gsm8k"
config = "main"
split = "test"
input = "question"
target = "answer"
"""
RECORDS = [{"question": "2+2?", "answer": "4"}, {"question": "3+3?", "answer": "6"}]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import huggingface_hub

    (tmp_path / "louped.toml").write_text(TOML + GSM8K_TABLE)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: None)
    return tmp_path


@pytest.fixture
def stub_hub(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """hf_dataset over RECORDS: the mapping turns each into a Sample, as on the Hub's rows."""
    asked: list[dict[str, Any]] = []

    def hf_dataset(path: str, split: str, name: str | None = None, sample_fields: Any = None,
                   **kw: Any) -> MemoryDataset:  # fmt: skip
        asked.append({"path": path, "split": split, "name": name, **kw})
        return MemoryDataset([sample_fields(r) for r in RECORDS], name=path)

    monkeypatch.setattr(generic, "hf_dataset", hf_dataset)
    return asked


def test_a_mapping_makes_each_row_a_sample() -> None:
    spec = Benchmark(dataset="x/y", input="q", target="a")
    sample = generic.record_to_sample(spec)({"q": "2+2?", "a": 4})
    assert sample.input == "2+2?" and sample.target == "4" and sample.choices is None
    aliases = generic.record_to_sample(spec)({"q": "Capital?", "a": ["Paris", "paris"]})
    assert aliases.target == ["Paris", "paris"]

    mc = Benchmark(dataset="x/y", input="q", target="a", choices="opts", scorer="choice")
    to_sample = generic.record_to_sample(mc)
    opts = ["red", "green", "blue"]
    assert to_sample({"q": "Grass?", "a": 1, "opts": opts}).target == "B"  # an index
    assert to_sample({"q": "Grass?", "a": "1", "opts": opts}).target == "B"
    assert to_sample({"q": "Grass?", "a": "c", "opts": opts}).target == "C"  # a letter
    assert to_sample({"q": "Grass?", "a": "green", "opts": opts}).choices == opts  # its text
    with pytest.raises(ValueError, match="not an index, a letter or the text"):
        to_sample({"q": "Grass?", "a": "purple", "opts": opts})
    with pytest.raises(ValueError, match="no field opts; its fields are a, q"):
        to_sample({"q": "Grass?", "a": 1})
    with pytest.raises(ValueError, match="not a list of choices"):
        to_sample({"q": "Grass?", "a": 1, "opts": "red"})
    with pytest.raises(ValueError, match="choice scorer needs a choices field"):
        Benchmark(dataset="x/y", input="q", target="a", scorer="choice")


def test_the_generic_task_reads_the_hub_dataset_by_the_mapping(
    project: Path, stub_hub: list[dict[str, Any]]
) -> None:
    task = generic.benchmark("gsm8k")
    assert task.name == "louped/gsm8k"
    assert [(s.input, s.target) for s in task.dataset] == [("2+2?", "4"), ("3+3?", "6")]
    assert stub_hub == [{"path": "openai/gsm8k", "split": "test", "name": "main",
                         "auto_id": True}]  # fmt: skip
    assert task.metadata == {"benchmark": "gsm8k", "dataset": "openai/gsm8k", "config": "main",
                             "split": "test", "input": "question", "target": "answer",
                             "scorer": "match"}  # fmt: skip
    with pytest.raises(ValueError, match=r"no \[benchmarks.nope\]"):
        generic.benchmark("nope")


def test_each_benchmark_is_registered_as_an_inspect_task(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from inspect_ai._util.registry import registry_lookup

    from louped.inspect_ext import _registry

    _registry._benchmarks()
    assert registry_lookup("task", "louped/gsm8k") is not None
    (project / "louped.toml").write_text('[benchmarks.Bad]\ndataset = "x/y"\n')
    with caplog.at_level(logging.WARNING):
        _registry._benchmarks()  # said, not raised: the louped/ provider must stay registered
    assert "benchmarks are not registered" in caplog.text


def run_benchmark(answers: list[str]) -> None:
    from inspect_ai import eval
    from inspect_ai.model import ModelOutput, get_model

    from louped.core import logs_dir

    outputs = [ModelOutput.from_content("mockllm/model", a) for a in answers]
    eval(generic.benchmark("gsm8k"), model=get_model("mockllm/model", custom_outputs=outputs),
         log_dir=str(logs_dir()), display="none")  # fmt: skip


def test_a_benchmarks_runs_are_its_leaderboard(
    project: Path, stub_hub: list[dict[str, Any]]
) -> None:
    run_benchmark(["The answer is 4", "It is 7"])
    run_benchmark(["4", "6"])
    api = client()
    tasks = {t["task"]: t for t in api.get("/api/evals").json()}
    assert tasks["louped/gsm8k"]["source"] == "benchmark"
    assert tasks["louped/gsm8k"]["about"] == ("openai/gsm8k (main), test: question to answer, "
                                              "scored by match.")  # fmt: skip
    rows = api.get("/api/benchmarks").json()
    first = rows[0]  # tasks with runs first
    assert first["task"]["task"] == "louped/gsm8k" and first["runs"] == 2
    assert first["best"]["score"] == 1.0 and first["best"]["metric"] == "match/accuracy"
    assert first["spec"]["dataset"] == "openai/gsm8k"
    assert all(r["runs"] == 0 for r in rows[1:])
    board = api.get("/api/benchmarks/board", params={"task": "gsm8k"}).json()  # its bare name
    assert [e["score"] for e in board["entries"]] == [1.0, 0.5]
    assert board["entries"][0]["model"] == "mockllm/model" and board["entries"][0]["samples"] == 2
    assert api.get("/api/benchmarks/board", params={"task": "nope"}).status_code == 404

    mcp = tools()
    assert call(mcp, "benchmarks", search="gsm8k")[0]["runs"] == 2
    assert len(call(mcp, "benchmark", name="louped/gsm8k")["entries"]) == 2


def test_a_project_tasks_runs_are_found_by_its_file(project: Path, isolated_home: Path) -> None:
    from inspect_ai import eval
    from inspect_ai.model import ModelOutput, get_model

    from louped.core import experiments_dir, logs_dir

    folder = experiments_dir() / "hello"
    folder.mkdir(parents=True)
    (folder / "task.py").write_text(
        "from inspect_ai import Task, task\nfrom inspect_ai.dataset import Sample\n"
        "from inspect_ai.scorer import includes\n\n@task\ndef hi():\n"
        "    return Task(dataset=[Sample(input='hi', target='hi')], scorer=includes())\n"
    )
    outputs = [ModelOutput.from_content("mockllm/model", "hi")]
    eval("experiments/hello/task.py", model=get_model("mockllm/model", custom_outputs=outputs),
         log_dir=str(logs_dir()), display="none")  # fmt: skip
    board = client().get("/api/benchmarks/board", params={"task": "experiments/hello/task.py@hi"})
    assert board.json()["entries"][0]["score"] == 1.0


def test_adding_a_benchmark_checks_its_mapping_and_keeps_it(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = Viewer(dict(GSM8K))
    monkeypatch.setattr(datasets, "_get", viewer)
    api = client()
    body = {"name": "gsm-train", "dataset": "openai/gsm8k", "config": "main", "split": "train",
            "input": "question", "target": "answer"}  # fmt: skip
    got = api.post("/api/benchmarks", json=body).json()
    assert got["checked"] is True and got["note"] is None
    assert got["benchmark"]["task"]["task"] == "louped/gsm-train"
    text = (project / "louped.toml").read_text()
    assert text.startswith(TOML + GSM8K_TABLE)  # what was there stays as it was
    assert tomllib.loads(text)["benchmarks"]["gsm-train"] == {
        "dataset": "openai/gsm8k", "config": "main", "split": "train", "input": "question",
        "target": "answer", "scorer": "match"}  # fmt: skip

    wrong = api.post("/api/benchmarks", json={**body, "target": "solution"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == ("openai/gsm8k has no field solution; its fields are "
                                      "question, answer, label, steps")  # fmt: skip
    split = api.post("/api/benchmarks", json={**body, "split": "dev"})
    assert "has no split dev; it has train, test" in split.json()["detail"]
    which = api.post("/api/benchmarks", json={**body, "config": None})
    assert "has configs main, socratic: name one" in which.json()["detail"]
    assert api.post("/api/benchmarks", json={**body, "name": "Bad Name"}).status_code == 422

    viewer.answers["/splits"] = (500, {"error": "down"})  # the viewer cannot answer: kept, said
    unchecked = api.post("/api/benchmarks", json={**body, "name": "gsm-train",
                                                  "scorer": "judge"}).json()  # fmt: skip
    assert unchecked["checked"] is False and "answered 500" in unchecked["note"]
    assert tomllib.loads((project / "louped.toml").read_text())["benchmarks"]["gsm-train"][
        "scorer"] == "judge"  # fmt: skip
    assert client(launching=False).post("/api/benchmarks", json=body).status_code == 403

    viewer.answers.update(GSM8K)
    mc = call(
        tools(),
        "add_benchmark",
        name="labels",
        dataset="openai/gsm8k",
        config="main",
        split="test",
        input="question",
        target="label",
        choices="steps",
        scorer="choice",
    )
    assert mc["benchmark"]["spec"]["choices"] == "steps"


def test_speed_benchmarks_by_model_and_setting(project: Path) -> None:
    from louped.analysis import line, table
    from louped.tracking import log_json, start_run

    def bench(model: str, tps: dict[str, list[float]]) -> None:
        with start_run("efficiency-bench", name=f"bench · {model}", params={"model": model}):
            rows = [[name, 900.0, "bfloat16", "cuda"] for name in tps]
            log_json(table("Weights", ["format", "weights MiB", "dtype", "device"], rows),
                     "views/00-bench.json")  # fmt: skip
            log_json(line("Throughput under load", [1, 4, 16], tps, "requests", "tokens/s"),
                     "views/01-bench.json")  # fmt: skip
            prefill = {k: [10.0, 40.0] for k in tps}
            log_json(line("Prefill by context", [512, 2048], prefill, "tokens", "ms"),
                     "views/03-bench.json")  # fmt: skip

    bench("tiny", {"as saved": [20, 70, 60], "int8": [15, 40, 80]})
    bench("other", {"as saved": [5, 9]})
    rows = client().get("/api/benchmarks/speed").json()
    assert [(r["model"], r["setting"]) for r in rows] == [
        ("other", "as saved"),
        ("tiny", "as saved"),
        ("tiny", "int8"),
    ]  # newest first
    tiny = {r["setting"]: r for r in rows if r["model"] == "tiny"}
    assert tiny["as saved"]["throughput"] == 70 and tiny["as saved"]["batch"] == 4
    assert tiny["int8"]["best"] and not tiny["as saved"]["best"]  # the fastest of its model
    assert tiny["int8"]["prefill_ms"] == 40 and tiny["int8"]["context"] == 2048
    assert tiny["int8"]["weights_mib"] == 900 and tiny["int8"]["device"] == "cuda"
    assert rows[0]["best"] and rows[0]["batch"] == 4
    assert [r["setting"] for r in call(tools(), "benchmarks", domain="efficiency")] == [
        "as saved", "as saved", "int8"]  # fmt: skip


def test_a_published_dashboard_keeps_the_lists(project: Path, tmp_path: Path) -> None:
    from louped.server.publish import key, publish

    (project / "louped.toml").write_text(GSM8K_TABLE)  # TOML's domain is not whole for /experiments
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><head></head></html>")
    done = publish(tmp_path / "site", web)
    assert done.failed == []
    for path in ("/datasets", "/benchmarks", "/benchmarks/speed"):
        assert (tmp_path / "site" / "api" / f"{key(path)}.json").exists()
