"""Regression cases as an Inspect task: a JSONL of questions with what the reply must do.

    {"id": "hours-1", "input": "When does the library open on Sunday?",
     "expect": {"tool": "search", "args": "library", "source": "library.example.edu",
                "mentions": ["10"], "not_mentions": ["search_knowledge"]}}
    {"id": "gpa", "input": "What is my GPA?", "expect": {"declines": true}}

Every expectation is optional: `tool` (a name or a list, each called at least once), `args` (text
in the arguments of a call, of the expected tool when one is given), `source` (text in a reported
source or, failing that, in the reply), `mentions` (all in the reply), `not_mentions` (none in the
reply), `declines` (the reply declines, or with false does not). `input` is a string or a list of
chat messages. The score is the share of the case's expectations met, each check itemized in its
metadata.

Tool calls and sources come from the transcript when the model called tools inside Inspect, and
from an agent/ model's reported trace (louped.inspect_ext.agent) when the agent ran them itself, so
the same cases score a local model with tools and an opaque system behind an endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageUser
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate

from louped.inspect_ext.scorers import is_refusal

#: Phrases that decline, beside the refusal prefixes.
DECLINES = ("don't know", "do not know", "don't have", "do not have", "not sure",
            "couldn't find", "could not find", "no information", "no access", "can't know",
            "cannot know", "unable to")  # fmt: skip

KEYS = ("tool", "args", "source", "mentions", "not_mentions", "declines")


def declines(text: str) -> bool:
    return is_refusal(text) or any(d in text.lower() for d in DECLINES)


def _messages(value: str | list[dict[str, Any]]) -> str | list[Any]:
    if isinstance(value, str):
        return value
    kinds = {"system": ChatMessageSystem, "user": ChatMessageUser,
             "assistant": ChatMessageAssistant}  # fmt: skip
    return [kinds[m["role"]](content=m["content"]) for m in value]


def trace(state: TaskState) -> tuple[list[tuple[str, str]], list[str]]:
    """The sample's tool calls as (name, arguments as JSON) and its reported sources: from the
    transcript's tool calls, then from an agent/ model's trace."""
    calls: list[tuple[str, str]] = []
    for m in state.messages:
        if isinstance(m, ChatMessageAssistant):
            for c in m.tool_calls or []:
                calls.append((c.function, json.dumps(c.arguments, sort_keys=True)))
    reported = (state.output.metadata or {}).get("trace") or {}
    for c in reported.get("tool_calls") or []:
        calls.append((str(c.get("name")), json.dumps(c.get("arguments"), sort_keys=True)))
    return calls, [str(s) for s in reported.get("sources") or []]


def check(expect: dict[str, Any], reply: str, calls: list[tuple[str, str]],
          sources: list[str]) -> dict[str, bool]:  # fmt: skip
    """Each expectation the case sets, met or not."""
    unknown = set(expect) - set(KEYS)
    if unknown:
        raise ValueError(f"unknown expectations {sorted(unknown)}; known: {', '.join(KEYS)}")
    text = reply.casefold()
    names = [n for n, _ in calls]
    out: dict[str, bool] = {}
    tool = expect.get("tool")
    wanted = [tool] if isinstance(tool, str) else list(tool or [])
    if "tool" in expect:
        out["tool"] = all(w in names for w in wanted)
    if "args" in expect:
        pool = [a for n, a in calls if not wanted or n in wanted]
        out["args"] = any(str(expect["args"]).casefold() in a.casefold() for a in pool)
    if "source" in expect:
        want = str(expect["source"]).casefold()
        out["source"] = any(want in s.casefold() for s in sources) or want in text
    if "mentions" in expect:
        out["mentions"] = all(str(m).casefold() in text for m in expect["mentions"])
    if "not_mentions" in expect:
        out["not_mentions"] = not any(str(m).casefold() in text for m in expect["not_mentions"])
    if "declines" in expect:
        out["declines"] = declines(reply) == bool(expect["declines"])
    return out


@scorer(metrics=[mean(), stderr()])
def expectations():
    """The share of the case's expectations the reply met."""

    async def score(state: TaskState, target: Target) -> Score:
        calls, sources = trace(state)
        met = check(state.metadata.get("expect") or {}, state.output.completion, calls, sources)
        if not met:
            raise ValueError(f"case {state.sample_id} sets no expectation")
        why = ", ".join(f"{k} {'ok' if v else 'missed'}" for k, v in met.items())
        return Score(value=sum(met.values()) / len(met), explanation=why,
                     answer=state.output.completion[:200], metadata=met)  # fmt: skip

    return score


def cases(path: str | Path, name: str | None = None) -> Task:
    """The cases in a JSONL file as a task: one generate, scored on their expectations."""
    path = Path(path)
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    data = [Sample(id=r.get("id", i + 1), input=_messages(r["input"]),
                   metadata={"expect": r.get("expect") or {}})
            for i, r in enumerate(rows)]  # fmt: skip
    return Task(dataset=data, solver=generate(), scorer=expectations(), name=name or path.stem)
