"""loupe endpoint-bench against fake OpenAI-compatible servers: streamed replies, usage counts,
records that line up across servers, and a server that fails without ending the sweep."""

import json

import httpx

from loupe import stores
from loupe.endpoint_bench import endpoint_bench
from loupe.stores.runs import read_artifact


def sse(*chunks: dict) -> bytes:
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"


def server(request: httpx.Request) -> httpx.Response:
    if request.url.host == "broken":
        return httpx.Response(500, text="no slot")
    body = json.loads(request.content)
    assert body["stream"] and body["stream_options"] == {"include_usage": True}
    words = [{"choices": [{"delta": {"content": w}}]} for w in ("a", " b", " c")]
    usage = {"choices": [], "usage": {"completion_tokens": 3}}
    if request.url.host == "nousage":
        usage = {"choices": []}
    return httpx.Response(200, content=sse(*words, usage),
                          headers={"content-type": "text/event-stream"})  # fmt: skip


def test_a_sweep_records_every_request_and_lines_servers_up() -> None:
    run_id = endpoint_bench(
        ["http://fast:8080/v1", "http://nousage:8081/v1", "http://broken:9/v1"], "m",
        levels=(1, 2), rounds=2, transport=httpx.MockTransport(server),
    )  # fmt: skip
    run = stores.get_run(run_id)
    files = {a.path for a in run.artifacts}
    assert {"raw/fast-8080.jsonl", "raw/nousage-8081.jsonl", "raw/broken-9.jsonl"} <= files
    fast = [json.loads(x) for x in read_artifact(run_id, "raw/fast-8080.jsonl").splitlines()]
    assert len(fast) == 6 and {r["concurrency"] for r in fast} == {1, 2}
    assert all(r["tokens"] == 3 and r["tokens_counted"] == "usage" and r["ttft_ms"] is not None
               for r in fast)  # fmt: skip
    counted = read_artifact(run_id, "raw/nousage-8081.jsonl").decode()
    assert '"tokens_counted": "deltas"' in counted and '"tokens": 3' in counted
    broken = [json.loads(x) for x in read_artifact(run_id, "raw/broken-9.jsonl").splitlines()]
    assert all(r["error"].startswith("RuntimeError: 500") for r in broken)
    # the same request ids in every file, so the Items tab lines the servers up
    assert [r["id"] for r in fast] == [r["id"] for r in broken]
    titles = [v.view.title for v in stores.list_views(run_id)]
    assert "Throughput by concurrency" in titles and "By endpoint and concurrency" in titles
    [summary] = [v.view for v in stores.list_views(run_id) if v.view.kind == "table"]
    assert summary.rows[-1][:2] == ["broken-9", 2] and summary.rows[-1][-1] == "4/4"  # type: ignore[union-attr]


def test_energy_is_measured_only_for_a_server_on_this_machine() -> None:
    from loupe.endpoint_bench import _meter

    meter, why = _meter("http://gpu-box.example:8080/v1")
    assert meter is None and why == "server is not on this machine"
