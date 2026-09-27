from pathlib import Path

from fastapi.testclient import TestClient

from loupe.server import create_app


def test_health() -> None:
    body = TestClient(create_app(), base_url="http://localhost").get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"]


def test_serves_the_ui_export(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>loupe</html>")
    client = TestClient(create_app(tmp_path), base_url="http://localhost")
    assert "loupe" in client.get("/").text
    assert client.get("/api/health").status_code == 200


def test_missing_ui_dir_serves_api_only(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "absent"), base_url="http://localhost")
    assert client.get("/").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_playground_without_a_model_says_so() -> None:
    client = TestClient(create_app(), base_url="http://localhost")
    assert client.get("/api/playground").json() == {"model": None, "layers": None}
    assert client.post("/api/playground/generate", json={"prompt": "hi"}).status_code == 409
    assert client.post("/api/playground/inspect", json={"prompt": "hi"}).status_code == 409


def test_inspect_view_is_served_read_only_over_the_eval_logs() -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample

    from loupe import stores
    from loupe.core import logs_dir

    eval(Task(dataset=[Sample(input="hi", target="hi")]), model="mockllm/model",
         log_dir=str(logs_dir()), display="none")  # fmt: skip
    client = TestClient(create_app(), base_url="http://localhost")
    (run,) = stores.list_runs()
    log = client.get(f"/api/runs/{run.id}").json()["log"]
    assert (logs_dir() / log).is_file()
    assert "Inspect View" in client.get("/inspect/").text
    files = client.get("/api/log-files").json()["files"]
    assert [f["name"].endswith(log) for f in files] == [True]
    name = files[0]["name"]
    assert client.get(f"/api/logs/{name}").status_code == 200
    assert client.get("/api/logs/file:///etc/passwd").status_code == 403
    before = (logs_dir() / log).read_bytes()
    viewer = {"X-Inspect-View-Request": "true"}  # what Inspect's own app sends on a write
    assert client.delete(f"/api/log-delete/{name}", headers=viewer).status_code == 403
    edit = {"edits": [{"type": "tags", "tags_add": ["x"]}], "provenance": {"author": "x"}}
    assert client.post(f"/api/log-edit/{name}", json=edit, headers=viewer).status_code == 403
    assert (logs_dir() / log).read_bytes() == before
    assert client.get("/api/health").status_code == 200


def test_circuit_graphs_are_listed_and_served_to_their_viewer() -> None:
    import json

    from loupe.core import graphs_dir, home

    client = TestClient(create_app(), base_url="http://localhost")
    assert client.get("/api/graphs").json() == []
    assert client.get("/circuit/").status_code == 404
    root = graphs_dir()
    (root / "viewer" / "index.html").write_text("<title>Attribution Graphs</title>")
    meta = {"graphs": [{"slug": "capital", "prompt": "The capital of France is", "scan": "s"}]}
    (root / "graph-metadata.json").write_text(json.dumps(meta))
    (root / "capital.json").write_text('{"nodes": [], "links": []}')
    (home() / "secret.json").write_text('"secret"')
    assert [g["slug"] for g in client.get("/api/graphs").json()] == ["capital"]
    assert "Attribution Graphs" in client.get("/circuit/").text
    assert client.get("/circuit/data/graph-metadata.json").json() == meta
    assert client.get("/circuit/graph_data/capital.json").json()["nodes"] == []
    for path in ["/circuit/graph_data/..%2Fsecret.json", "/circuit/data/../secret.json",
                 "/circuit/graph_data/%2e%2e/secret.json"]:  # fmt: skip
        assert "secret" not in client.get(path).text


def test_only_this_machine_is_answered() -> None:
    assert TestClient(create_app()).get("/api/health").status_code == 400
    assert TestClient(create_app(), base_url="http://127.0.0.1").get("/api/health").is_success
