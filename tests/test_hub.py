"""The Hugging Face Hub in the app and the MCP, with HfApi stood in for: no test reaches the Hub."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
import huggingface_hub
import pytest
from fastapi.testclient import TestClient
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError
from huggingface_hub.hf_api import DatasetInfo, ModelInfo, PaperInfo
from test_agent import call, tools

from louped import sources
from louped.server import create_app, hub
from louped.sources import Source

TOML = '# my project\n\n[domains.honesty]\naxis = "behavior"  # what it studies\n'


def model(id: str, task: str = "text-generation", downloads: int = 10, **more: Any) -> ModelInfo:
    given = {"likes": 2, "library_name": "transformers", "gated": False, "private": False,
             "lastModified": "2025-01-01T00:00:00.000Z"} | more  # fmt: skip
    return ModelInfo(id=id, downloads=downloads, pipeline_tag=task, **given)


def refused(status: int) -> HfHubHTTPError:
    request = httpx.Request("GET", "https://huggingface.co/api/whoami-v2")
    return HfHubHTTPError(f"{status} refused", response=httpx.Response(status, request=request))


class FakeApi:
    """HfApi's calls the Hub routes make, answering from fixed data and recording the asks."""

    asked: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    who: ClassVar[dict[str, Any] | Exception] = {}
    tmp: ClassVar[str] = ""

    def list_models(self, **kw: Any) -> list[ModelInfo]:
        self.asked.append(("models", kw))
        if kw["pipeline_tag"] == "sentence-similarity":
            return [model("BAAI/bge-small", "sentence-similarity", 50)]
        if kw["pipeline_tag"] == "feature-extraction":
            return [model("intfloat/e5", "feature-extraction", 90)]
        safetensors = {"parameters": {"BF16": 494_000_000}, "total": 494_000_000}
        return [model("Qwen/Qwen2.5-0.5B", gated="manual", safetensors=safetensors)]

    def list_datasets(self, **kw: Any) -> list[DatasetInfo]:
        self.asked.append(("datasets", kw))
        return [DatasetInfo(id="openai/gsm8k", downloads=5, likes=1, gated=False, private=False)]

    def list_papers(self, **kw: Any) -> list[PaperInfo]:
        self.asked.append(("papers", kw))
        return [PaperInfo(id="2310.13548", title="Sycophancy", authors=[{"name": "M. Sharma"}],
                          upvotes=7)]  # fmt: skip

    def list_daily_papers(self, **kw: Any) -> list[PaperInfo]:
        self.asked.append(("daily", kw))
        return [PaperInfo(paper={"id": "2501.00001", "authors": []}, title="Today")]

    def model_info(self, id: str, **kw: Any) -> ModelInfo:
        if id == "nobody/none":
            request = httpx.Request("GET", "https://huggingface.co/api/models/nobody/none")
            raise RepositoryNotFoundError("404", response=httpx.Response(404, request=request))
        return model(id, cardData={"license": "apache-2.0"}, tags=["text-generation"],
                     siblings=[{"rfilename": "README.md"}, {"rfilename": "model.safetensors"}],
                     usedStorage=988_000_000)  # fmt: skip

    def paper_info(self, id: str) -> PaperInfo:
        return PaperInfo(id=id, title="Sycophancy", authors=[{"name": "M. Sharma"}],
                         summary="Models agree.", githubRepo="https://github.com/x/y")  # fmt: skip

    def hf_hub_download(self, id: str, filename: str, repo_type: str) -> str:
        path = Path(self.tmp) / "README.md"
        path.write_text("---\nlicense: apache-2.0\n---\n# Qwen\n\nA small model.\n")
        return str(path)

    def whoami(self) -> dict[str, Any]:
        if isinstance(self.who, Exception):
            raise self.who
        return self.who


@pytest.fixture
def hub_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> type[FakeApi]:
    (tmp_path / "louped.toml").write_text(TOML)
    monkeypatch.chdir(tmp_path)
    FakeApi.asked, FakeApi.tmp = [], str(tmp_path)
    FakeApi.who = {"name": "ash", "avatarUrl": "/avatars/a.png"}
    monkeypatch.setattr(hub, "_api", FakeApi)
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: "hf_x")
    return FakeApi


def client(launching: bool = True) -> TestClient:
    return TestClient(create_app(launching=launching), base_url="http://localhost")


def test_a_search_says_what_each_model_dataset_and_paper_is(hub_api: type[FakeApi]) -> None:
    api = client()
    asked = {"kind": "models", "q": "qwen", "task": "text-generation",
             "library": "transformers", "sort": "likes"}  # fmt: skip
    [m] = api.get("/api/hub/search", params=asked).json()
    assert m["id"] == "Qwen/Qwen2.5-0.5B" and m["gated"] and m["params"] == 494_000_000
    assert m["url"] == "https://huggingface.co/Qwen/Qwen2.5-0.5B" and m["library"] == "transformers"
    _, asked = hub_api.asked[-1]
    assert asked["search"] == "qwen" and asked["pipeline_tag"] == "text-generation"
    assert asked["filter"] == "transformers" and asked["sort"] == "likes"

    # embeddings: both embedding tasks, merged by the sort and cut to the limit
    found = api.get("/api/hub/search", params={"kind": "embeddings", "limit": 1}).json()
    assert [e["id"] for e in found] == ["intfloat/e5"] and found[0]["kind"] == "embeddings"
    bad = api.get("/api/hub/search", params={"kind": "embeddings", "task": "text-generation"})
    assert bad.status_code == 400

    [d] = api.get("/api/hub/search", params={"kind": "datasets", "sort": "recent"}).json()
    assert d["url"] == "https://huggingface.co/datasets/openai/gsm8k"
    assert hub_api.asked[-1][1]["sort"] == "last_modified"
    assert api.get("/api/hub/search", params={"kind": "datasets", "task": "x"}).status_code == 400

    [p] = api.get("/api/hub/search", params={"kind": "papers", "q": "sycophancy"}).json()
    assert p["title"] == "Sycophancy" and p["authors"] == ["M. Sharma"] and p["upvotes"] == 7
    [today] = api.get("/api/hub/search", params={"kind": "papers"}).json()
    assert today["id"] == "2501.00001" and hub_api.asked[-1][0] == "daily"


def test_the_detail_reads_the_card_license_and_links(hub_api: type[FakeApi]) -> None:
    api = client()
    got = api.get("/api/hub/info", params={"kind": "models", "id": "Qwen/Qwen2.5-0.5B"}).json()
    assert got["card"] == "# Qwen\n\nA small model." and got["license"] == "apache-2.0"
    assert got["files"] == 2 and got["size"] == 988_000_000
    paper = api.get("/api/hub/info", params={"kind": "papers", "id": "2310.13548"}).json()
    assert paper["summary"] == "Models agree." and paper["links"] == {
        "arxiv": "https://arxiv.org/abs/2310.13548",
        "github": "https://github.com/x/y",
    }
    assert api.get("/api/hub/info", params={"kind": "papers", "id": "x/y"}).status_code == 400
    missing = api.get("/api/hub/info", params={"kind": "models", "id": "nobody/none"})
    assert missing.status_code == 404 and "not on the Hub" in missing.json()["detail"]


def test_hub_errors_are_said_not_crashed(hub_api: type[FakeApi], monkeypatch) -> None:
    def down(self: FakeApi, **kw: Any) -> list[ModelInfo]:
        raise httpx.ConnectError("proxy said no")

    monkeypatch.setattr(FakeApi, "list_models", down)
    got = client().get("/api/hub/search", params={"kind": "models"})
    assert got.status_code == 502 and "could not reach" in got.json()["detail"]

    def no(self: FakeApi, **kw: Any) -> list[ModelInfo]:
        raise refused(401)

    monkeypatch.setattr(FakeApi, "list_models", no)
    assert client().get("/api/hub/search", params={"kind": "models"}).status_code == 401


def test_the_account_and_a_new_token(hub_api: type[FakeApi], monkeypatch) -> None:
    api = client()
    assert api.get("/api/hub/me").json() == {
        "token": True, "name": "ash", "avatar": "https://huggingface.co/avatars/a.png",
        "error": None}  # fmt: skip
    hub_api.who = refused(401)  # a token that no longer works is said
    me = api.get("/api/hub/me").json()
    assert me["token"] and me["name"] is None and "refused the token" in me["error"]

    saved: list[str] = []
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: None)
    assert api.get("/api/hub/me").json()["token"] is False

    def whoami(token: str) -> dict[str, str]:
        if token != "hf_good":
            raise refused(401)
        return {"name": "ash"}

    monkeypatch.setattr(huggingface_hub, "whoami", whoami)
    monkeypatch.setattr(huggingface_hub, "login", lambda token, **_: saved.append(token))
    assert api.post("/api/hub/token", json={"token": " hf_good "}).json()["name"] == "ash"
    assert saved == ["hf_good"]
    bad = api.post("/api/hub/token", json={"token": "hf_bad"})
    assert bad.status_code == 400 and "did not accept" in bad.json()["detail"]
    form = api.post("/api/hub/token", data={"token": "hf_good"})  # not JSON: refused
    assert form.status_code == 415
    exposed = client(launching=False)
    assert exposed.get("/api/hub/me").status_code == 403
    assert exposed.post("/api/hub/token", json={"token": "hf_good"}).status_code == 403


def test_adding_lists_it_in_louped_toml_and_a_download_is_a_job(
    hub_api: type[FakeApi], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from louped.server.launch import Jobs

    monkeypatch.setattr(Jobs, "work", lambda self: None)  # queued, never run: no download here
    api = client()
    assert api.get("/api/hub/added").json() == {"models": [], "embeddings": [], "datasets": []}
    got = api.post("/api/hub/add", json={"kind": "models", "id": "Qwen/Qwen2.5-0.5B"}).json()
    assert got["added"]["models"] == ["Qwen/Qwen2.5-0.5B"] and got["job"] is None
    api.post("/api/hub/add", json={"kind": "models", "id": "Qwen/Qwen2.5-0.5B"})  # once
    api.post("/api/hub/add", json={"kind": "embeddings", "id": "BAAI/bge-small"})
    text = (tmp_path / "louped.toml").read_text()
    assert text.startswith(TOML)  # the comments and tables there stay as they were
    assert text.endswith('[hub]\nembeddings = ["BAAI/bge-small"]\nmodels = ["Qwen/Qwen2.5-0.5B"]\n')
    assert api.get("/api/hub/added").json()["embeddings"] == ["BAAI/bge-small"]

    done = api.post("/api/hub/add", json={"kind": "datasets", "id": "openai/gsm8k",
                                          "download": True}).json()  # fmt: skip
    job = done["job"]
    assert job["title"] == "louped hub get openai/gsm8k --dataset"
    assert job["argv"][1:] == ["hub", "get", "openai/gsm8k", "--dataset"]
    assert api.get("/api/launch/jobs").json()[0]["id"] == job["id"]  # shown on Runs
    assert api.post("/api/hub/add", json={"kind": "models", "id": "a b"}).status_code == 422

    (tmp_path / "louped.toml").write_text('[hub]\nmodels = "Qwen"\n')
    assert api.get("/api/hub/added").status_code == 400


def test_a_paper_becomes_a_source(hub_api: type[FakeApi], monkeypatch) -> None:
    kept: list[str] = []

    def add_url(url: str) -> Source:
        kept.append(url)
        return Source(key="arxiv-2310.13548", title="Sycophancy", kind="pdf", file="x.pdf",
                      origin=url, sha256="0", added=datetime(2025, 1, 1, tzinfo=UTC),
                      pages=1)  # fmt: skip

    monkeypatch.setattr(sources, "add_url", add_url)
    api = client()
    got = api.post("/api/hub/add", json={"kind": "papers", "id": "2310.13548"}).json()
    assert got["source"]["key"] == "arxiv-2310.13548"
    assert kept == ["https://arxiv.org/abs/2310.13548"]
    body = {"kind": "papers", "id": "2310.13548", "download": True}
    assert api.post("/api/hub/add", json=body).status_code == 400


def test_louped_hub_get_downloads_through_huggingface_hub(monkeypatch, capsys) -> None:
    from louped.cli import main

    got: list[tuple[str, str | None]] = []

    def download(repo: str, repo_type: str | None = None) -> str:
        got.append((repo, repo_type))
        return "/cache/x"

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    monkeypatch.setattr("sys.argv", ["louped", "hub", "get", "openai/gsm8k", "--dataset"])
    main()
    assert got == [("openai/gsm8k", "dataset")] and capsys.readouterr().out.strip() == "/cache/x"


def test_launch_forms_offer_the_added_models(hub_api: type[FakeApi]) -> None:
    api = client()
    hub_form = {o["flag"]: o for o in api.get("/api/launch/options?id=hub").json()}
    assert hub_form["action"]["choices"] == ["get"] and hub_form["--dataset"]["kind"] == "bool"
    sweep = {o["flag"]: o for o in api.get("/api/launch/options?id=sweep").json()}
    assert sweep["--model"]["suggest"] == "models"


def test_an_agent_searches_reads_and_adds_from_the_hub(hub_api: type[FakeApi]) -> None:
    mcp = tools()
    [m] = call(mcp, "hub_search", kind="models", query="qwen")
    assert m["id"] == "Qwen/Qwen2.5-0.5B"
    assert call(mcp, "hub_info", kind="models", id="Qwen/Qwen2.5-0.5B")["license"] == "apache-2.0"
    added = call(mcp, "hub_add", kind="models", id="Qwen/Qwen2.5-0.5B")
    assert added["added"]["models"] == ["Qwen/Qwen2.5-0.5B"] and added["job"] is None
