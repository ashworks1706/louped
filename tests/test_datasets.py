"""The Datasets pages: the Hub datasets louped.toml lists (with their domains), files under data/,
the training sets louped reads, and one dataset's card, splits, features and first rows. HfApi
and the Hub's dataset viewer are stood in for: no test reaches the Hub."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from huggingface_hub.hf_api import DatasetInfo
from test_agent import call, tools
from test_hub import TOML, FakeApi, client

from louped.server import datasets, hub

#: What the viewer answers, by route; an Exception is raised, a (status, body) pair answered.
GSM8K: dict[str, Any] = {
    "/splits": {
        "splits": [
            {"dataset": "openai/gsm8k", "config": "main", "split": "train"},
            {"dataset": "openai/gsm8k", "config": "main", "split": "test"},
            {"dataset": "openai/gsm8k", "config": "socratic", "split": "test"},
        ]
    },
    "/info": {
        "dataset_info": {
            "features": {
                "question": {"dtype": "string", "_type": "Value"},
                "answer": {"dtype": "string", "_type": "Value"},
                "label": {"names": ["no", "yes"], "_type": "ClassLabel"},
                "steps": {"feature": {"dtype": "int64", "_type": "Value"}, "_type": "List"},
            },
            "splits": {
                "train": {"name": "train", "num_examples": 7473},
                "test": {"name": "test", "num_examples": 1319},
            },
        }
    },
    "/first-rows": {
        "features": [
            {"feature_idx": 0, "name": "question", "type": {"dtype": "string", "_type": "Value"}}
        ],
        "rows": [
            {
                "row_idx": i,
                "row": {"question": f"q{i}", "answer": f"#### {i}"},
                "truncated_cells": [],
            }
            for i in range(30)
        ],
    },
}


class Viewer:
    """The dataset viewer's answers, recording each ask with its headers."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.asked: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str], headers: dict[str, str]) -> httpx.Response:
        path = url.removeprefix(datasets.VIEWER)
        self.asked.append((path, params, headers))
        found = self.answers.get(path, (404, {"error": "Not found."}))
        if isinstance(found, Exception):
            raise found
        status, body = found if isinstance(found, tuple) else (200, found)
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))


class DatasetApi(FakeApi):
    def dataset_info(self, id: str, **kw: Any) -> DatasetInfo:
        return DatasetInfo(id=id, downloads=900, likes=3, gated=False, private=False,
                           cardData={"license": "mit"}, tags=["task_categories:qa"],
                           siblings=[{"rfilename": "README.md"}],
                           usedStorage=5_000_000)  # fmt: skip


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import huggingface_hub

    (tmp_path / "louped.toml").write_text(TOML)
    monkeypatch.chdir(tmp_path)
    DatasetApi.asked, DatasetApi.tmp = [], str(tmp_path)
    monkeypatch.setattr(hub, "_api", DatasetApi)
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: "hf_x")
    return tmp_path


@pytest.fixture
def viewer(monkeypatch: pytest.MonkeyPatch) -> Viewer:
    found = Viewer(dict(GSM8K))
    monkeypatch.setattr(datasets, "_get", found)
    return found


def write_data(root: Path) -> None:
    data = root / "data"
    (data / "evals").mkdir(parents=True)
    (data / "pairs.jsonl").write_text('{"prompt": "2+2?", "answer": 4}\n{"prompt": "3+3?"}\n')
    (data / "evals" / "scores.csv").write_text("model,score\nbase,0.5\ndpo,0.75\n")
    (data / "notes.txt").write_text("not a dataset")
    (data / ".cache").mkdir()
    (data / ".cache" / "x.jsonl").write_text("{}\n")


def test_the_list_holds_hub_datasets_with_domains_and_files_under_data(project: Path) -> None:
    hub_table = '[hub]\ndatasets = ["openai/gsm8k", "a/b"]\n\n[hub.domains]\n'
    (project / "louped.toml").write_text(f'{TOML}\n{hub_table}"openai/gsm8k" = ["behavior"]\n')
    write_data(project)
    got = client().get("/api/datasets").json()
    assert [(d["id"], d["source"], d["domains"]) for d in got] == [
        ("openai/gsm8k", "hub", ["behavior"]),
        ("a/b", "hub", []),
        ("data/evals/scores.csv", "local", []),
        ("data/pairs.jsonl", "local", []),
    ]
    assert got[3]["format"] == "jsonl" and got[3]["size"] > 0
    (project / "louped.toml").write_text('[hub]\ndatasets = ["a/b"]\n[hub.domains]\n"a/b" = "x"\n')
    bad = client().get("/api/datasets")
    assert bad.status_code == 400 and "[hub.domains]" in bad.json()["detail"]


def test_a_training_set_louped_reads_is_listed_too(project: Path, isolated_home: Path) -> None:
    sets = isolated_home / "data" / "pushback"
    sets.mkdir(parents=True)
    row = {"prompt": [{"role": "user", "content": "2+2?"}], "chosen": "4", "rejected": "5"}
    (sets / "pairs.jsonl").write_text(json.dumps(row) + "\n")
    [found] = client().get("/api/datasets").json()
    assert found["source"] == "training" and found["id"] == "pairs.jsonl" and found["rows"] == 1


def test_adding_a_dataset_to_a_domain_keeps_louped_toml_valid(project: Path) -> None:

    api = client()
    body = {"kind": "datasets", "id": "openai/gsm8k", "domains": ["efficiency"]}
    assert api.post("/api/hub/add", json=body).json()["added"]["datasets"] == ["openai/gsm8k"]
    api.post("/api/hub/add", json={**body, "domains": ["behavior"]})  # added to what it had
    api.post("/api/hub/add", json={"kind": "models", "id": "Qwen/Qwen2.5-0.5B"})
    text = (project / "louped.toml").read_text()
    assert text.startswith(TOML)
    assert '[hub.domains]\n"openai/gsm8k" = ["behavior", "efficiency"]\n' in text
    import tomllib

    assert tomllib.loads(text)["hub"]["models"] == ["Qwen/Qwen2.5-0.5B"]
    [d] = api.get("/api/datasets").json()
    assert d["domains"] == ["behavior", "efficiency"]
    model = api.post("/api/hub/add", json={"kind": "models", "id": "a/b", "domains": ["behavior"]})
    assert model.status_code == 400 and "only a dataset" in model.json()["detail"]
    paper = api.post("/api/hub/add", json={"kind": "papers", "id": "2310.13548",
                                           "domains": ["behavior"]})  # fmt: skip
    assert paper.status_code == 400


def test_a_hub_datasets_card_splits_features_and_first_rows(project: Path, viewer: Viewer) -> None:
    got = client().get("/api/datasets/hub", params={"id": "openai/gsm8k", "rows": 5}).json()
    assert got["hub"]["license"] == "mit" and got["hub"]["downloads"] == 900
    assert got["hub"]["card"] == "# Qwen\n\nA small model."  # FakeApi's README
    assert got["config"] == "main" and got["split"] == "train" and got["total"] == 7473
    assert [(s["config"], s["split"], s["rows"]) for s in got["splits"]] == [
        ("main", "train", 7473), ("main", "test", 1319), ("socratic", "test", None)]  # fmt: skip
    assert {f["name"]: f["type"] for f in got["features"]} == {
        "question": "string", "answer": "string", "label": "class_label(no, yes)",
        "steps": "list<int64>"}  # fmt: skip
    assert [r["question"] for r in got["rows"]] == ["q0", "q1", "q2", "q3", "q4"]
    assert got["error"] is None and got["hub_error"] is None
    path, params, headers = viewer.asked[-1]
    assert path == "/first-rows" and params == {"dataset": "openai/gsm8k", "config": "main",
                                                "split": "train"}  # fmt: skip
    assert headers == {"Authorization": "Bearer hf_x"}  # gated datasets need the token

    test = client().get("/api/datasets/hub", params={"id": "openai/gsm8k", "split": "test"})
    assert test.json()["total"] == 1319
    wrong = client().get("/api/datasets/hub", params={"id": "openai/gsm8k", "split": "dev"})
    assert wrong.json()["error"] == "no split dev in main; it has train, test"
    assert wrong.json()["rows"] == []


def test_what_the_viewer_cannot_read_is_said_with_its_reason(
    project: Path, viewer: Viewer, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer.answers["/splits"] = (501, {"error": "The dataset viewer is not available for this "
                                                "dataset."})  # fmt: skip
    got = client().get("/api/datasets/hub", params={"id": "openai/gsm8k"}).json()
    assert got["rows"] == [] and got["hub"]["license"] == "mit"
    assert got["error"] == ("the dataset viewer answered 501 for /splits: The dataset viewer is "
                            "not available for this dataset.")  # fmt: skip
    viewer.answers["/splits"] = httpx.ConnectError("proxy said no")
    got = client().get("/api/datasets/hub", params={"id": "openai/gsm8k"}).json()
    assert got["error"].startswith("could not reach the dataset viewer")

    def missing(self: DatasetApi, id: str, **kw: Any) -> DatasetInfo:
        from huggingface_hub.errors import RepositoryNotFoundError

        request = httpx.Request("GET", "https://huggingface.co/api/datasets/x/y")
        raise RepositoryNotFoundError("404", response=httpx.Response(404, request=request))

    monkeypatch.setattr(DatasetApi, "dataset_info", missing)
    viewer.answers.update(GSM8K)
    got = client().get("/api/datasets/hub", params={"id": "openai/gsm8k"}).json()
    assert "not on the Hub" in got["hub_error"] and got["rows"]  # the rows still show
    assert client().get("/api/datasets/hub", params={"id": "a b"}).status_code == 400
    exposed = client(launching=False)
    assert exposed.get("/api/datasets/hub", params={"id": "openai/gsm8k"}).status_code == 403
    assert exposed.get("/api/datasets").status_code == 200  # the list reads only files


def test_a_files_columns_and_first_rows(project: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    write_data(project)
    pq.write_table(pa.table({"q": ["a", "b", "c"], "n": [1, 2, 3]}), project / "data" / "t.parquet")
    api = client()
    got = api.get("/api/datasets/local", params={"path": "data/pairs.jsonl"}).json()
    assert got["total"] == 2 and got["rows"][0] == {"prompt": "2+2?", "answer": 4}
    assert got["features"] == [{"name": "prompt", "type": "string"},
                               {"name": "answer", "type": "int64"}]  # fmt: skip
    csv = api.get("/api/datasets/local", params={"path": "data/evals/scores.csv"}).json()
    assert csv["rows"][1] == {"model": "dpo", "score": 0.75}
    parquet = api.get("/api/datasets/local", params={"path": "data/t.parquet", "rows": 2}).json()
    assert parquet["total"] == 3 and parquet["rows"] == [{"q": "a", "n": 1}, {"q": "b", "n": 2}]
    assert parquet["features"] == [{"name": "q", "type": "string"},
                                   {"name": "n", "type": "int64"}]  # fmt: skip

    (project / "data" / "broken.jsonl").write_text('{"a": 1}\nnot json\n')
    broken = api.get("/api/datasets/local", params={"path": "data/broken.jsonl"}).json()
    assert broken["rows"] == [] and broken["error"].startswith("data/broken.jsonl line 2 is not")
    assert api.get("/api/datasets/local", params={"path": "louped.toml"}).status_code == 404
    assert api.get("/api/datasets/local", params={"path": "../x.jsonl"}).status_code in (400, 404)


def test_a_big_file_previews_from_its_first_lines(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_data(project)
    monkeypatch.setattr(datasets, "MAX_PARSE", 10)
    got = client().get("/api/datasets/local", params={"path": "data/pairs.jsonl", "rows": 1})
    assert got.json()["rows"] == [{"prompt": "2+2?", "answer": 4}] and got.json()["total"] is None


def test_an_agent_lists_reads_and_adds_datasets(project: Path, viewer: Viewer) -> None:
    write_data(project)
    mcp = tools()
    added = call(mcp, "hub_add", kind="datasets", id="openai/gsm8k", domains=["behavior"])
    assert added["added"]["datasets"] == ["openai/gsm8k"]
    assert [d["id"] for d in call(mcp, "datasets", domain="efficiency")] == [
        "data/evals/scores.csv", "data/pairs.jsonl"]  # fmt: skip
    assert len(call(mcp, "datasets", domain="behavior")) == 3
    one = call(mcp, "dataset", id="openai/gsm8k", split="test", rows=2)
    assert one["split"] == "test" and len(one["rows"]) == 2 and one["hub"]["license"] == "mit"
    local = call(mcp, "dataset", id="data/pairs.jsonl")
    assert local["source"] == "local" and local["total"] == 2
