"""Degenerate replies, found in any eval's samples as louped reads them, with no task change.

The reply is the conversation's last assistant message with text. It is flagged when it:

- repeat: says what an earlier assistant turn of the same conversation said. That is the same
  text after lowercasing and collapsing whitespace, or a word-level similarity (difflib's ratio
  on the word lists) of REPEAT_RATIO or more.
- echo: copies the system prompt or the chat template. It holds ECHO_WORDS consecutive words of
  a system message (the whole message when it is shorter, from ECHO_MIN words), or a template
  marker anywhere (MARKERS), or opens with a role name and a colon (ROLE_OPENING).
- loop: repeats itself. One run of LOOP_N tokens (a word, or a run of punctuation), with a word
  in it, occurs LOOP_TIMES times or more.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from louped.data.pairs import normalize, words
from louped.stores.types import Degenerate as Flag

REPEAT_RATIO = 0.9
ECHO_WORDS = 20
ECHO_MIN = 5
LOOP_N = 8
LOOP_TIMES = 3
MARKERS = ("<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>", "<|im_start|>",
           "<|im_end|>", "[INST]", "[/INST]", "<start_of_turn>", "<end_of_turn>",
           "<|endoftext|>")  # fmt: skip
ROLE_OPENING = re.compile(r"^\s*(assistant|user|system|human)\s*:", re.I)


def repeats(reply: str, earlier: list[str]) -> bool:
    said, tokens = normalize(reply), words(reply)
    for turn in earlier:
        if not normalize(turn):
            continue
        if normalize(turn) == said:
            return True
        match = SequenceMatcher(None, words(turn), tokens, autojunk=False)
        if match.real_quick_ratio() >= REPEAT_RATIO and match.ratio() >= REPEAT_RATIO:
            return True
    return False


def echoes(reply: str, system: list[str]) -> bool:
    if any(m in reply for m in MARKERS) or ROLE_OPENING.match(reply):
        return True
    tokens = words(reply)
    for text in system:
        source = words(text)
        if len(source) < ECHO_MIN:
            continue
        n = min(ECHO_WORDS, len(source))
        spans = {tuple(source[i : i + n]) for i in range(len(source) - n + 1)}
        if any(tuple(tokens[i : i + n]) in spans for i in range(len(tokens) - n + 1)):
            return True
    return False


def loops(reply: str) -> bool:
    tokens = words(reply)
    grams = Counter(tuple(tokens[i : i + LOOP_N]) for i in range(len(tokens) - LOOP_N + 1))
    # a run of punctuation only is formatting (a table's rule), not a loop
    return any(k >= LOOP_TIMES and any(t[0].isalnum() for t in g) for g, k in grams.items())


def flags(messages: list[tuple[str, str]]) -> list[Flag]:
    """The flags of a conversation's reply, from its (role, text) messages in order."""
    turns = [i for i, (role, text) in enumerate(messages) if role == "assistant" and text.strip()]
    if not turns:
        return []
    reply = messages[turns[-1]][1]
    earlier = [messages[i][1] for i in turns[:-1]]
    system = [text for role, text in messages if role == "system"]
    found: list[Flag] = []
    if repeats(reply, earlier):
        found.append("repeat")
    if echoes(reply, system):
        found.append("echo")
    if loops(reply):
        found.append("loop")
    return found
