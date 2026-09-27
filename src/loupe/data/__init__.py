"""Training sets from real model calls: export, redact, verify, review, curate.

Any source becomes an `Example`, one model call in the OpenAI chat wire shape, so the rest of the
pipeline and the trainer never see where it came from. Standard library and pydantic only; the
Phoenix source needs httpx and review needs rich (the data extra).
"""

from loupe.data.example import (
    Example,
    conversation,
    fingerprint,
    read_jsonl,
    tool_call,
    write_jsonl,
)

__all__ = [
    "Example",
    "conversation",
    "fingerprint",
    "read_jsonl",
    "tool_call",
    "write_jsonl",
]
