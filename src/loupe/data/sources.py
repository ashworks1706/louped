"""Where examples come from. Each source turns one product's record of a model call into Examples.

- `generation_traces`: JSONL trace files with one `generation` event per model call (zipy).
- `phoenix`: OpenTelemetry GenAI spans in a self-hosted Arize Phoenix (SparkyAI).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loupe.data.example import Example, tool_call


class SourceError(RuntimeError):
    """A source could not be read, or held a record that is not a model call."""


# generation_traces ---------------------------------------------------------------------------


def _at(raw: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _generation(record: dict[str, Any], index: int) -> Example | None:
    if record.get("event") != "generation":
        return None
    data = record.get("data") or {}
    messages = data.get("input")
    if not isinstance(messages, list):
        return None
    meta = {
        "source": "generation_traces",
        "model": str(data.get("model") or ""),
        "org": str(record.get("org_id") or ""),
        "platform": str(record.get("platform") or ""),
    }
    return Example(
        id=f"{record.get('request_id', '')}:{index}",
        messages=messages,
        reply=str(data.get("output") or ""),
        tool_calls=[tool_call(c) for c in data.get("tool_calls") or [] if isinstance(c, dict)],
        meta={k: v for k, v in meta.items() if v},
        at=_at(record.get("at", "")),
    )


def _trace(path: Path) -> list[Example]:
    out: list[Example] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        example = _generation(record, len(out)) if isinstance(record, dict) else None
        if example is not None:
            out.append(example)
    return out


def generation_traces(directory: Path, max_age_days: int = 0) -> list[Example]:
    """Every generation under <directory>/<org>/<request>.jsonl, newest first. 0 days reads all."""
    if not directory.is_dir():
        raise SourceError(f"no traces under {directory}")
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days) if max_age_days else None

    def files() -> Iterator[Path]:
        found = sorted(directory.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in found:
            if cutoff and datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) < cutoff:
                return
            yield path

    return [example for path in files() for example in _trace(path)]


# phoenix -------------------------------------------------------------------------------------

_INPUT, _OUTPUT, _MODEL = "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.request.model"
_SESSION, _KIND = "session.id", "sparky.span"
_SUMMARY_LEAD = "Summary of earlier turns: "


def attribute(attrs: Any, key: str) -> Any:
    """One attribute by dotted name, whether Phoenix stored it flat or nested."""
    if not isinstance(attrs, dict):
        return None
    if key in attrs:
        return attrs[key]
    node: Any = attrs
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _json(value: Any, what: str, span: str) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SourceError(f"span {span}: {what} is not JSON: {exc}") from exc


def _text(items: list[Any], key: str, span: str) -> str:
    texts = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "text":
            raise SourceError(f"span {span}: unsupported message part {item!r:.200}")
        texts.append(str(item.get(key, "")))
    return "".join(texts)


def _message(raw: Any, span: str) -> dict[str, Any]:
    """One message in the OpenAI shape, from a flat, a parts or a content-list message."""
    if not isinstance(raw, dict) or "role" not in raw:
        raise SourceError(f"span {span}: bad message {raw!r:.200}")
    data = dict(raw)
    if "parts" in data:
        data["content"] = _text(data.pop("parts"), "content", span)
    elif isinstance(data.get("content"), list):
        data["content"] = _text(data["content"], "text", span)
    if data["role"] == "summary":  # the engine sends summaries as a system message with a lead
        data["role"], data["content"] = "system", f"{_SUMMARY_LEAD}{data.get('content', '')}"
    if data.get("tool_calls"):
        data["tool_calls"] = [tool_call(c) for c in data["tool_calls"]]
    else:
        data.pop("tool_calls", None)
    if "tool_name" in data:
        data["name"] = data.pop("tool_name")
    return {k: v for k, v in data.items() if v is not None}


def span_example(span: dict[str, Any]) -> Example | None:
    """One llm span as an example; other and unfinished spans are None, malformed ones raise."""
    span_id = span.get("id") or (span.get("context") or {}).get("span_id")
    if not span_id:
        raise SourceError(f"span without an id: {span!r:.200}")
    attrs = span.get("attributes")
    if not isinstance(attrs, dict):
        return None
    kind = attribute(attrs, _KIND)
    if (kind if kind is not None else span.get("name")) != "llm":
        return None
    raw_in, raw_out = attribute(attrs, _INPUT), attribute(attrs, _OUTPUT)
    if raw_in in (None, "", []) or raw_out in (None, "", []):
        return None
    messages = [_message(m, span_id) for m in _json(raw_in, _INPUT, span_id)]
    choices = [_message(m, span_id) for m in _json(raw_out, _OUTPUT, span_id)]
    if not choices:
        return None
    reply = choices[0]
    meta = {"source": "phoenix", "model": attribute(attrs, _MODEL),
            "session": attribute(attrs, _SESSION)}  # fmt: skip
    return Example(
        id=str(span_id),
        messages=messages,
        reply=str(reply.get("content") or ""),
        tool_calls=reply.get("tool_calls", []),
        meta={k: str(v) for k, v in meta.items() if v},
        at=_at(span.get("start_time", "")),
    )


def phoenix(
    url: str,
    project: str,
    api_key: str = "",
    page_size: int = 500,
    timeout: float = 30.0,
    transport: Any = None,
) -> list[Example]:
    """Every complete llm span of a Phoenix project, paged through its REST API."""
    import httpx

    endpoint = f"{url.rstrip('/')}/v1/projects/{project}/spans"
    headers = {"accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    out: list[Example] = []
    cursor: str | None = None
    with httpx.Client(timeout=timeout, transport=transport) as client:
        while True:
            params: dict[str, Any] = {"limit": page_size, "name": "llm"}
            if cursor:
                params["cursor"] = cursor
            try:
                r = client.get(endpoint, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise SourceError(f"phoenix request failed: {exc}") from exc
            if r.status_code != 200:
                raise SourceError(f"phoenix returned {r.status_code}: {r.text[:200]}")
            body = r.json()
            page = body.get("data")
            if not isinstance(page, list):
                raise SourceError("unexpected spans response: data is not a list")
            out.extend(e for e in map(span_example, page) if e is not None)
            cursor = body.get("next_cursor") or None
            if cursor is None or not page:
                return out
