"""What the person picked in the app (Shift+click), as text for their agent's next message.

`louped picks` prints the picks. `louped picks --hook` is a Claude Code UserPromptSubmit hook
(`louped init` writes it to .claude/settings.json): it adds the picks to the message the person
just sent, so the agent sees them without being asked to look. It adds them when they changed
since the agent last read them, or when the message says @sel (every pick) or @sel 2 or
@sel 1,3 (those picks, numbered as the tray numbers them). Each read is marked on the server,
and the tray says the agent has read them.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

#: @sel, or @sel with pick numbers: @sel 2, @sel 1,3.
SEL = re.compile(r"(?<!\w)@sel(?:\s+(\d+(?:\s*,\s*\d+)*))?(?!\w)")
#: How much of a part's data goes in the message; ui_selection gives all of it.
DATA_CHARS = 2000


def asked(prompt: str) -> list[int] | None:
    """The picks a message asks for with @sel: [] for every pick, the numbers given, or None
    when it does not say @sel."""
    found = [m.group(1) for m in SEL.finditer(prompt)]
    if not found:
        return None
    if any(g is None for g in found):
        return []
    return sorted({int(n) for g in found for n in g.split(",")})


def describe(parts: list[dict[str, Any]], numbers: list[int]) -> str:
    """The picks as numbered text: what each is, where it is, and its data."""
    blocks = []
    for n in numbers:
        p = parts[n - 1]
        lines = [f"pick {n}: louped part {p['id']}", f"page: {p['url']}"]
        lines += [f"{k}: {p[k]}" for k in ("run", "experiment") if p.get(k)]
        if p.get("text"):
            lines.append(f"shows: {p['text'][:200]}")
        if p.get("data") is not None:
            lines.append(f"data: {json.dumps(p['data'])[:DATA_CHARS]}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


HEAD = (
    "The person picked these parts in louped's app (Shift+click); the tray numbers them. "
    "ui_selection gives each part's full data."
)


def current(api: httpx.Client) -> dict[str, Any] | None:
    """The picks the server keeps (parts, version, read), or None before the first pick."""
    return api.get("/ui/selection").raise_for_status().json()


def mark_read(api: httpx.Client, picks: dict[str, Any]) -> None:
    api.post("/ui/selection/read", json={"version": picks["version"]}).raise_for_status()


def for_prompt(api: httpx.Client, prompt: str) -> str | None:
    """The text to add to a message: the picks it asks for, or the picks the agent has not
    read; None when there is nothing to add. Marks the picks read."""
    want = asked(prompt)
    try:
        picks = current(api)
    except httpx.HTTPError as e:
        if want is None:
            return None  # nothing was asked for, and with no app there are no picks
        return f"The message says @sel, but louped's app at {api.base_url} did not answer: {e}"
    parts = picks["parts"] if picks else []
    if want is None and (not picks or not parts or picks["read"] >= picks["version"]):
        return None
    if not picks or not parts:
        return "The message says @sel, but nothing is picked in louped's app."
    numbers = want or list(range(1, len(parts) + 1))
    missing = [n for n in numbers if not 1 <= n <= len(parts)]
    if missing:
        named = ", ".join(map(str, missing))
        return f"The message asks for pick {named}, but the tray holds picks 1 to {len(parts)}."
    mark_read(api, picks)
    return f"{HEAD}\n\n{describe(parts, numbers)}"


def hook_output(context: str | None) -> str:
    """Claude Code's UserPromptSubmit output: the context to add, or nothing."""
    if context is None:
        return ""
    event = {"hookEventName": "UserPromptSubmit", "additionalContext": context}
    return json.dumps({"hookSpecificOutput": event})
