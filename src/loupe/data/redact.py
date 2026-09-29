"""Removing the people in a conversation before it becomes a training set.

Deterministic regexes, no model: an email, a phone number, a platform id, a leaked token. A dataset
outlives the conversation it came from. Add your own with `extra`: a named pattern from EXTRA, or
any regex, replaced by [redacted].
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from loupe.data.example import Example

Pattern = tuple[re.Pattern[str], str]

PATTERNS: tuple[Pattern, ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?<!\d)(?:\+?\d{1,2}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)"), "[phone]"),
    (re.compile(r"<@!?\d{17,20}>"), "[mention]"),
    (re.compile(r"(?<!\d)\d{17,20}(?!\d)"), "[platform-id]"),
    (re.compile(r"\bxox[baprs]-[\w-]{10,}", re.I), "[token]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[token]"),
    (re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{20,}\b"), "[token]"),
)

#: Named extras to switch on from the command line.
EXTRA: dict[str, Pattern] = {
    # a 10-digit number standing alone, such as a student or employee id
    "id-10": (re.compile(r"(?<![A-Za-z0-9])\d{10}(?![A-Za-z0-9])"), "[id]"),
}

_KEEP = {"id", "role", "type", "name", "tool_call_id"}  # structure, not content


def redact_text(text: str, patterns: Sequence[Pattern] = PATTERNS) -> str:
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


def _value(value: Any, patterns: Sequence[Pattern], key: str = "") -> Any:
    if isinstance(value, str):
        return value if key in _KEEP else redact_text(value, patterns)
    if isinstance(value, list):
        return [_value(v, patterns) for v in value]
    if isinstance(value, dict):
        return {k: _value(v, patterns, k) for k, v in value.items()}
    return value


def redact(example: Example, extra: Sequence[str] = ()) -> Example:
    """The example with messages, reply and tool-call arguments redacted, and no user in meta."""
    own = [EXTRA.get(x) or (re.compile(x), "[redacted]") for x in extra]
    patterns = (*own, *PATTERNS)  # specific before generic
    return example.model_copy(
        update={
            "messages": _value(example.messages, patterns),
            "reply": redact_text(example.reply, patterns),
            "tool_calls": _value(example.tool_calls, patterns),
            "meta": {k: v for k, v in example.meta.items() if k != "user"},
        }
    )
