"""Runs pushed to a remote from one louped and pulled into another."""

from pathlib import Path

import pytest

from louped import stores, sync
from louped.analysis import views


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
