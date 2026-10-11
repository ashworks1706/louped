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


def test_publish_keeps_the_tables_a_runs_board_reads(tmp_path: Path) -> None:
    import mlflow

    from louped.server.publish import _enc
    from louped.stores.types import BoardView
    from louped.tracking import start_run

    with start_run("q", name="r") as r:
        mlflow.log_text('{"a": 1}\n', "raw/rows.jsonl")
    ref = f"run:m-{r.info.run_id}/raw/rows.jsonl"
    board = {"kind": "board", "title": "b", "data": {"t": {"ref": ref}},
             "panels": [{"id": "p", "kind": "table", "data": "t"}]}  # fmt: skip
    stores.add_view(f"m-{r.info.run_id}", "b", BoardView.model_validate(board))
    web = tmp_path / "web"
    web.mkdir()
    done = publish(tmp_path / "site", web)
    assert done.failed == []
    table = tmp_path / "site" / "api" / f"{key(f'/board/table?ref={_enc(ref)}')}.json"
    assert json.loads(table.read_text())["rows"] == [{"a": 1}]
