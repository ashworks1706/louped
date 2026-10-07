"""Runs pushed to a remote from one louped and pulled into another."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from louped import stores, sync
from louped.analysis import views
from louped.cli import _connect
from louped.server import create_app


@pytest.mark.usefixtures("two_runs")
def test_runs_pushed_from_one_louped_are_pulled_into_another_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = str(tmp_path / "remote")
    monkeypatch.setenv("LOUPED_REMOTE", remote)
    monkeypatch.setenv("LOUPED_HOST", "laptop")
    mine = {r.id for r in stores.list_runs()}
    pushed = sync.push()
    assert pushed.bundle and set(pushed.runs) == mine
    assert sync.push().bundle is None  # nothing new
    assert sync.pull() == []  # its own bundle is no news

    monkeypatch.setenv("LOUPED_HOME", str(tmp_path / "other"))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)  # mlflow.set_tracking_uri sets it
    [(name, added)] = sync.pull()
    assert name == pushed.bundle and added.host == "laptop" and len(added.runs) == 2
    runs = {r.id: r for r in stores.list_runs()}
    assert {r.host for r in runs.values()} == {"laptop"}
    tracked = next(r for r in runs.values() if r.id.startswith("m-"))
    assert stores.get_run(tracked.id).metrics["loss"] == 0.5
    assert [v.view.title for v in stores.list_views(tracked.id)] == ["t"]
    assert sync.pull() == []
    assert sync.push().bundle is None  # what was pulled is some other louped's to push


def test_a_remote_must_be_set_and_a_vega_view_must_carry_its_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOUPED_REMOTE", raising=False)
    with pytest.raises(ValueError, match="no remote"):
        sync.push()
    spec = {"mark": "bar", "data": {"values": [{"x": 1}]}, "encoding": {"x": {"field": "x"}}}
    assert views.vega("v", spec)["kind"] == "vega"
    with pytest.raises(ValueError, match="inline"):
        views.vega("v", {"layer": [{"data": {"url": "https://example.com/x.csv"}}]})


def test_a_relative_remote_is_the_projects_and_a_missing_one_is_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOUPED_REMOTE", raising=False)
    (tmp_path / "louped.toml").write_text('remote = "runs"\n')
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    assert sync.configured() == str(tmp_path / "runs")
    assert sync.is_local(str(tmp_path / "runs")) and not sync.is_local("memory://x")
    with pytest.raises(ValueError, match="does not exist"):
        sync.pull()
    (tmp_path / "louped.toml").write_text("remote = [\n")
    with pytest.raises(ValueError, match=r"louped\.toml"):
        sync.configured()


def test_a_vega_view_may_carry_a_url_column_in_its_rows() -> None:
    spec = {"mark": "point", "data": {"values": [{"url": "https://x", "y": 1}]}}
    assert views.vega("v", spec)["spec"] == spec


TOML = """# a project

[domains.honesty]
axis = "behavior"
"""


def test_an_hf_bucket_remote_asks_for_a_token_and_connect_sets_one_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import huggingface_hub

    monkeypatch.delenv("LOUPED_REMOTE", raising=False)
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "louped.toml").write_text(TOML)
    monkeypatch.chdir(tmp_path / "proj")
    signed: list[str] = []
    made: list[tuple[str, bool]] = []
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: signed[-1] if signed else None)
    monkeypatch.setattr(huggingface_hub, "whoami", lambda token=None: {"name": "ash"})
    monkeypatch.setattr(huggingface_hub, "login", lambda token, **_: signed.append(token))

    def create(bucket: str, private: bool, exist_ok: bool) -> None:
        made.append((bucket, private))

    monkeypatch.setattr(huggingface_hub, "create_bucket", create)

    assert sync.bucket("hf://buckets/ash/runs/sub") == "ash/runs" and sync.bucket("s3://b") is None
    with pytest.raises(ValueError, match="<user>/<name>"):
        sync.bucket("hf://buckets/ash")
    with pytest.raises(sync.NeedsToken):
        sync.push("hf://buckets/ash/runs")
    api = TestClient(create_app(launching=True), base_url="http://localhost")
    assert api.post("/api/launch/push", json={}).status_code == 400  # no remote at all
    monkeypatch.setenv("LOUPED_REMOTE", "hf://buckets/ash/runs")
    assert api.post("/api/launch/pull", json={}).status_code == 401  # the app asks for a token
    monkeypatch.delenv("LOUPED_REMOTE")
    assert api.post("/api/launch/remote", json={}).status_code == 401

    # the app: a token and no remote make a private bucket of the account, named for the project
    got = api.post("/api/launch/remote", json={"token": "hf_x"})
    assert got.json() == {"remote": "hf://buckets/ash/proj", "token": True}, got.text
    assert signed == ["hf_x"] and made == [("ash/proj", True)]
    text = (tmp_path / "proj" / "louped.toml").read_text()
    assert text.startswith('# a project\n\nremote = "hf://buckets/ash/proj"\n\n[domains.honesty]')
    sync.set_remote("runs")  # set again: replaced, not added
    assert sync.configured() == str(tmp_path / "proj" / "runs")
    assert (tmp_path / "proj" / "louped.toml").read_text().count("remote =") == 1

    # the terminal: asked for the remote, and for a token only when an hf:// one needs it
    (tmp_path / "proj" / "louped.toml").write_text(TOML)
    signed.clear()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr("getpass.getpass", lambda _: "hf_y ")
    _connect(None)
    assert signed == ["hf_y"] and sync.configured() == "hf://buckets/ash/proj"
    _connect(None)  # set up: nothing asked again
    assert signed == ["hf_y"]


def test_a_big_artifact_stays_in_the_remote_and_is_fetched_once_when_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    import mlflow

    from louped.analysis import table
    from louped.tracking import log_json, start_run

    monkeypatch.chdir(tmp_path)
    (tmp_path / "louped.toml").write_text("large_artifact_mb = 0.01\n")  # 10 KiB
    remote = tmp_path / "remote"
    monkeypatch.setenv("LOUPED_REMOTE", str(remote))
    (tmp_path / "weights.bin").write_bytes(b"x" * 50_000)
    with start_run("hello", name="big"):
        log_json(table("t", ["a"], [[1]]), "views/00-t.json")
        mlflow.log_artifact(str(tmp_path / "weights.bin"), "out")
    sync.push()

    other = tmp_path / "other"
    monkeypatch.setenv("LOUPED_HOME", str(other))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    [(_, added)] = sync.pull()
    [run_id] = added.runs
    files = {a.path: a.size for a in stores.get_run(run_id).artifacts}
    assert files["out/weights.bin"] == 50_000 and "louped.remote.json" not in files
    assert not list(other.rglob("weights.bin"))  # listed, not copied
    assert [v.view.title for v in stores.list_views(run_id)] == ["t"]  # small files came
    assert not list((other / "staging").iterdir())  # pulled through staging, cleaned after

    api = TestClient(create_app(), base_url="http://localhost")
    url = f"/api/runs/{run_id}/artifacts/out/weights.bin"
    got = api.get(url)
    assert got.status_code == 200 and got.content == b"x" * 50_000
    [cached] = list((other / "remote-cache").rglob("weights.bin"))
    shutil.rmtree(remote)  # fetched once: the cached copy serves without the remote
    assert api.get(url).content == b"x" * 50_000
    cached.unlink()
    gone = api.get(url)
    assert gone.status_code == 502 and "could not be read" in gone.json()["detail"]
    (tmp_path / "louped.toml").write_text('large_artifact_mb = "big"\n')
    with pytest.raises(ValueError, match="number of MB"):
        sync.large()
