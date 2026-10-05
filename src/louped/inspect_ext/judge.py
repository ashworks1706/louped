"""Pairwise judging: a model reads two runs' answers to the same samples and picks the better one.

Each pair is judged twice, once in each order, since a judge favours a position. B's win is the mean
over the two orders (B 1, A 0, tie 0.5); consistent says the two orders agreed; parsed says both
replies ended in a verdict, and a reply without one counts as a tie, so read parsed first. The
judge is the task's model, so any Inspect model judges: louped/ and hf/ run locally.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.log import EvalSample, read_eval_log_samples
from inspect_ai.model import ChatMessageAssistant, ChatMessageUser, get_model
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import Generate, TaskState, solver

from louped.core.judges import CRITERION, POINTS, PROMPT, pair_key, request_text

VERDICT = re.compile(r"verdict\s*:\s*\**\s*(1|2|tie)\b", re.I)


def verdict(reply: str) -> str | None:
    """ "1", "2" or "tie" from the reply's last verdict line, None when it gave none."""
    found = VERDICT.findall(reply)
    return found[-1].lower() if found else None


def _key(s: EvalSample) -> str:
    return pair_key(s.id, s.epoch)


def pairs(a: str | Path, b: str | Path) -> list[Sample]:
    """The samples both logs answered without error, each with A's and B's final answer."""
    left = {_key(s): s for s in read_eval_log_samples(a) if s.error is None}
    right = {_key(s): s for s in read_eval_log_samples(b) if s.error is None}
    return [
        Sample(id=k, input=request_text(s.input),
               metadata={"a": s.output.completion, "b": right[k].output.completion})
        for k, s in left.items()
        if k in right
    ]  # fmt: skip


@solver
def _judge(criterion: str, prompt: str, parse: Callable[[str], str | None]):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        judge = get_model()
        state.messages = []  # the transcript is the judge's two exchanges; the request is in each
        winners: list[str | None] = []
        for first, second in (("a", "b"), ("b", "a")):
            ask = prompt.format(request=state.input_text, first=state.metadata[first],
                                second=state.metadata[second], criterion=criterion)  # fmt: skip
            reply = (await judge.generate(ask)).completion
            state.messages += [ChatMessageUser(content=ask), ChatMessageAssistant(content=reply)]
            pick = parse(reply)
            if pick not in ("1", "2", "tie", None):
                raise ValueError(f"the judge's verdict() gave {pick!r}: 1, 2, tie or None")
            winners.append({"1": first, "2": second, "tie": "tie"}.get(pick or ""))
        state.metadata["winners"] = winners
        return state

    return solve


@scorer(metrics=[mean(), stderr()])
def b_wins():
    """B's win over the two orders: 1 both B, 0 both A, ties and splits between."""

    async def score(state: TaskState, target: Target) -> Score:
        winners = state.metadata["winners"]
        value = sum(POINTS[w or "tie"] for w in winners) / len(winners)
        return Score(value=value, explanation=f"A first: {winners[0]}; B first: {winners[1]}")

    return score


@scorer(metrics=[mean(), stderr()])
def consistent():
    """Both orders named the same winner."""

    async def score(state: TaskState, target: Target) -> Score:
        first, second = state.metadata["winners"]
        return Score(value=float(first is not None and first == second))

    return score


@scorer(metrics=[mean(), stderr()])
def parsed():
    """Share of the judge's replies that ended in a verdict."""

    async def score(state: TaskState, target: Target) -> Score:
        winners = state.metadata["winners"]
        return Score(value=sum(w is not None for w in winners) / len(winners))

    return score


def pairwise(a: str | Path, b: str | Path, criterion: str = CRITERION, prompt: str = PROMPT,
             parse: Callable[[str], str | None] = verdict) -> Task:  # fmt: skip
    """Two eval logs' shared samples, each judged in both orders: prompt filled with the request,
    the two answers and criterion, the reply read by parse ("1", "2", "tie" or None)."""
    data = pairs(a, b)
    if not data:
        raise ValueError(f"{a} and {b} share no samples answered without error")
    return Task(dataset=data, solver=_judge(criterion, prompt, parse),
                scorer=[b_wins(), consistent(), parsed()], name="judge")  # fmt: skip
