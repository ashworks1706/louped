"""The dashboard written as static files."""

import json
from pathlib import Path

import pytest

from louped import stores
from louped.server.publish import key, publish


@pytest.mark.usefixtures("two_runs")
def test_publish_writes_every_answer_the_pages_ask_for(tmp_path: Path) -> None:
    web = tmp_path / "web"
    (web / "runs").mkdir(parents=True)
    (web / "index.html").write_text("<html><head></head><body></body></html>")
    (web / "runs" / "index.html").write_text("<html><head></head></html>")
    out = tmp_path / "site"
    done = publish(out, web)
    assert done.runs == 2
    assert 'name="louped-snapshot"' in (out / "runs" / "index.html").read_text()
    assert key("/runs/e-a?epoch=1") == ",2Fruns,2Fe-a,3Fepoch,3D1"  # encodeURIComponent's way
    assert key("/runs/e-a/samples/" + "x" * 300).startswith("h-")  # too long for a file name
    assert done.failed == []
    health = json.loads((out / "api" / f"{key('/health')}.json").read_text())
    assert health["launching"] is False and health["remote"] is None
    for run in stores.list_runs():
        assert (out / "api" / f"{key(f'/runs/{run.id}')}.json").exists()
        assert (out / "api" / f"{key(f'/runs/{run.id}/views')}.json").exists()
    evaled = next(r for r in stores.list_runs() if r.id.startswith("e-"))
    assert (out / "api" / f"{key(f'/runs/{evaled.id}/samples/1?epoch=1')}.json").exists()
    assert (out / "inspect" / "index.html").exists() and list((out / "inspect/logs").glob("*.eval"))
    with pytest.raises(ValueError, match="not empty"):
        publish(out, web)
