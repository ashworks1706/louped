"""The data pipeline: sources, redaction, verification, review and curation."""

import json
from pathlib import Path

import httpx
import pytest

from louped.data import (
    Example,
    conversation,
    curate,
    fingerprint,
    read_jsonl,
    redact,
    sources,
    tool_call,
    verify,
    write_jsonl,
)

SYSTEM = {"role": "system", "content": "s"}
USER = {"role": "user", "content": "hi"}


def ex(id: str = "a", reply: str = "hello", messages=None, calls=None) -> Example:
    return Example(id=id, messages=messages or [SYSTEM, USER], reply=reply, tool_calls=calls or [])


# sources: generation traces ---------------------------------------------------------------------


def test_generation_traces_skip_other_events_and_number_calls(tmp_path: Path) -> None:
    org = tmp_path / "org1" / "day"  # any depth
    org.mkdir(parents=True)
    gen = {
        "event": "generation",
        "request_id": "r1",
        "group": "team-a",
        "data": {
            "input": [SYSTEM, USER],
            "output": "hey",
            "model": "m",
            "tool_calls": [{"name": "calendar", "arguments": {"day": "mon"}}],
        },
    }
    lines = [{"event": "request"}, gen, gen, "not json"]
    (org / "r1.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    found = sources.generation_traces(tmp_path)
    assert [e.id for e in found] == ["r1:0", "r1:1"]
    assert found[0].meta == {
        "source": "generation_traces",
        "model": "m",
        "group": "team-a",
    }
    call = found[0].tool_calls[0]["function"]
    assert call == {"name": "calendar", "arguments": '{"day": "mon"}'}
    with pytest.raises(sources.SourceError):
        sources.generation_traces(tmp_path / "absent")


# sources: phoenix -----------------------------------------------------------------------------


def span(id: str, out=None, kind="LLM", **attrs) -> dict:
    base = {
        "openinference.span.kind": kind,
        "gen_ai.input.messages": json.dumps(
            [
                SYSTEM,
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "h"}, {"type": "text", "text": "i"}],
                },
            ]
        ),
        "gen_ai.output.messages": json.dumps(out or [{"role": "assistant", "content": "yo"}]),
        "gen_ai.request.model": "m",
        "session.id": "s1",
        "user.id": "u1",
    }
    return {"id": id, "name": "llm", "attributes": {**base, **attrs}}


def test_phoenix_span_maps_to_the_openai_shape() -> None:
    out = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "search", "arguments": {"q": "x"}}],
        }
    ]
    e = sources.span_example(span("s1", out))
    assert e is not None
    assert e.messages[1] == {"role": "user", "content": "hi"}
    assert e.tool_calls == [
        {"id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"q": "x"}'}}
    ]
    assert e.meta == {"source": "phoenix", "model": "m", "session": "s1"}
    assert sources.span_example(span("s2", kind="TOOL")) is None
    own = span("s3", **{"app.span": "llm", "openinference.span.kind": None})
    del own["attributes"]["openinference.span.kind"]
    own["name"] = "chat"
    assert sources.span_example(own) is None  # neither the default attribute nor the name
    assert sources.span_example(own, kind_key="app.span") is not None


def test_phoenix_summary_becomes_a_system_message() -> None:
    s = span("s1")
    s["attributes"]["gen_ai.input.messages"] = json.dumps([{"role": "summary", "content": "x"}])
    e = sources.span_example(s)
    assert e is not None
    assert e.messages == [{"role": "system", "content": "Summary of earlier turns: x"}]


def test_phoenix_pages_through_the_cursor_with_the_key() -> None:
    pages = {None: ([span("a"), span("b")], "c2"), "c2": ([span("c")], None)}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        data, cursor = pages[request.url.params.get("cursor")]
        return httpx.Response(200, json={"data": data, "next_cursor": cursor})

    found = sources.phoenix(
        "http://px:6006/", "chat", "k", 2, transport=httpx.MockTransport(handler)
    )
    assert [e.id for e in found] == ["a", "b", "c"]
    assert seen[0].url.path == "/v1/projects/chat/spans" and "name" not in seen[0].url.params
    assert seen[0].headers["authorization"] == "Bearer k"

    def fail(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(sources.SourceError, match="500"):
        sources.phoenix("http://px", "p", transport=httpx.MockTransport(fail))


# redact, verify, curate ---------------------------------------------------------------------


def test_redact_people_and_tokens_but_not_structure() -> None:
    e = ex(
        messages=[
            SYSTEM,
            {"role": "user", "content": "mail a.b@c.io or call 480-555-1234 <@123456789012345678>"},
        ],
        reply="token sk-abcdefghijklmnopqrstu",
        calls=[
            tool_call(
                {"id": "call_123456789012345678", "name": "send", "arguments": {"to": "x@y.com"}}
            )
        ],
    )
    e.meta["user"] = "u1"
    r = redact.redact(e)
    assert r.messages[1]["content"] == "mail [email] or call [phone] [mention]"
    assert r.reply == "token [token]"
    assert r.tool_calls[0]["id"] == "call_123456789012345678"
    assert "[email]" in r.tool_calls[0]["function"]["arguments"]
    assert "user" not in r.meta
    assert redact.redact(ex(reply="id 1234567890"), ["id-10"]).reply == "id [id]"
    assert redact.redact(ex(reply="ticket AB-1234"), [r"AB-\d+"]).reply == "ticket [redacted]"


def test_verify_counts_each_reason() -> None:
    bad_call = tool_call({"name": "", "arguments": {}})
    examples = [
        ex("a"),
        ex("b"),
        ex("c", messages=[USER]),
        ex("d", messages=[SYSTEM]),
        ex("e", reply=""),
        ex("f", reply="", calls=[bad_call]),
    ]
    kept, reasons = verify.verify(examples)
    assert [e.id for e in kept] == ["a", "c"]
    assert reasons == {
        "duplicate": 1,
        "no user turn": 1,
        "empty reply": 1,
        "tool call without a name": 1,
    }


def test_ledger_keeps_fixes_drops_and_catches_stale(tmp_path: Path) -> None:
    a, b, c, d, stale = ex("a", "1"), ex("b", "2"), ex("c", "3"), ex("d", "4"), ex("e", "5")
    ledger = curate.Ledger()
    ledger.record(curate.decide(a, "keep", "", "ash"))
    fixed = curate.decide(b, "fix", "tone", "ash")
    fixed.reply = "better"
    ledger.record(fixed)
    ledger.record(curate.decide(c, "drop", "wrong", "ash"))
    ledger.record(curate.decide(ex("e", "old"), "keep", "", "ash"))
    path = tmp_path / "decisions.jsonl"
    curate.save(path, ledger)
    ledger = curate.load(path)

    accepted, counts = curate.apply([a, b, c, d, stale], ledger)
    assert [(e.id, e.reply) for e in accepted] == [("a", "1"), ("b", "better")]
    assert [e.meta["review"] for e in accepted] == ["kept by ash", "fixed by ash"]
    assert counts == {"kept": 1, "fixed": 1, "dropped": 1, "unreviewed": 1, "stale": 1}
    assert [e.id for e in curate.pending([a, d, stale], ledger)] == ["d", "e"]


def test_jsonl_round_trip_and_conversation(tmp_path: Path) -> None:
    e = ex(calls=[tool_call({"name": "t", "arguments": "{}"})])
    write_jsonl(tmp_path / "x.jsonl", [e])
    (back,) = read_jsonl(tmp_path / "x.jsonl")
    assert fingerprint(back) == fingerprint(e)
    assert conversation(e)[-1] == {
        "role": "assistant",
        "content": "hello",
        "tool_calls": e.tool_calls,
    }
    with pytest.raises(FileNotFoundError, match="step before"):
        read_jsonl(tmp_path / "missing.jsonl")
