from pathlib import Path

from fastapi.testclient import TestClient

from loupe.server import create_app


def test_health() -> None:
    body = TestClient(create_app()).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"]


def test_serves_the_ui_export(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>loupe</html>")
    client = TestClient(create_app(tmp_path))
    assert "loupe" in client.get("/").text
    assert client.get("/api/health").status_code == 200


def test_missing_ui_dir_serves_api_only(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "absent"))
    assert client.get("/").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_playground_without_a_model_says_so() -> None:
    client = TestClient(create_app())
    assert client.get("/api/playground").json() == {"model": None, "layers": None}
    assert client.post("/api/playground/generate", json={"prompt": "hi"}).status_code == 409
    assert client.post("/api/playground/inspect", json={"prompt": "hi"}).status_code == 409
