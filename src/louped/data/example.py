"""One model call as a training example, and the reviewer's judgment about it."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["keep", "drop", "fix"]
VERDICTS: tuple[Verdict, ...] = ("keep", "drop", "fix")


class Example(BaseModel):
    """The messages a model was sent and what it replied, in the OpenAI chat wire shape."""

    #: Stable across exports of the same source, so a decision about it survives a re-export.
    id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    reply: str = ""
    #: OpenAI shape: {"id", "type": "function", "function": {"name", "arguments": str}}.
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    #: Where it came from: source, model, org, platform, session. Never trained on.
    meta: dict[str, str] = Field(default_factory=dict)
    at: datetime | None = None


class Decision(BaseModel):
    """One judgment about one example, tied to the example as it was judged."""

    id: str
    verdict: Verdict
    reason: str = ""
    #: The reply as it should have been; set only for fix.
    reply: str | None = None
    fingerprint: str = ""
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    by: str = ""


def tool_call(call: dict[str, Any]) -> dict[str, Any]:
    """A tool call in the OpenAI shape, from it or from a flat {name, arguments, id} one."""
    if isinstance(call.get("function"), dict):
        return call
    arguments = call.get("arguments", {})
    return {
        "id": str(call.get("id") or ""),
        "type": "function",
        "function": {
            "name": str(call.get("name") or ""),
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
        },
    }


def text_of(message: dict[str, Any]) -> str:
    """The text of one wire message, whether it is a string or a content array."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def conversation(example: Example) -> list[dict[str, Any]]:
    """The messages plus the reply, ready for a chat template."""
    reply: dict[str, Any] = {"role": "assistant", "content": example.reply}
    if example.tool_calls:
        reply["tool_calls"] = example.tool_calls
    return [*example.messages, reply]


def fingerprint(example: Example) -> str:
    """A hash of what would be trained on; the id and meta do not count."""
    payload = json.dumps(
        {"m": example.messages, "r": example.reply, "t": example.tool_calls},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def read_jsonl(path: Path) -> list[Example]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist yet; run the step before this one")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Example.model_validate_json(line) for line in lines if line.strip()]


def write_jsonl(path: Path, examples: list[Example]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(e.model_dump_json() + "\n" for e in examples), encoding="utf-8")
