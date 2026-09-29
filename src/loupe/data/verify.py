"""Keeping only examples worth judging: well-formed, not empty, not duplicates."""

from __future__ import annotations

from loupe.data.example import Example, fingerprint


def reject_reason(example: Example) -> str | None:
    """Why an example cannot be trained on, or None."""
    if not example.messages:
        return "no messages"
    roles = [m.get("role") for m in example.messages]
    if "user" not in roles:
        return "no user turn"
    if not example.reply.strip() and not example.tool_calls:
        return "empty reply"
    for call in example.tool_calls:
        if not (call.get("function") or {}).get("name"):
            return "tool call without a name"
    return None


def verify(examples: list[Example]) -> tuple[list[Example], dict[str, int]]:
    """The examples worth judging, and a count of each reason the rest were dropped."""
    kept: list[Example] = []
    reasons: dict[str, int] = {}
    seen: set[str] = set()
    for example in examples:
        reason = reject_reason(example)
        if reason is None:
            mark = fingerprint(example)
            reason = "duplicate" if mark in seen else None
            seen.add(mark)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            kept.append(example)
    return kept, reasons
