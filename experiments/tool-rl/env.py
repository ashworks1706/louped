"""The environment this experiment trains in: a calculator and a submit tool over one problem.

TRL makes one instance per rollout, calls reset with the row's fields, exposes calculate and submit
as tools, and adds get_reward to the rewards once the episode ends.

`stated` is a second reward, over the reply's text: half credit for a correct number stated
without submitting. A small model at first answers in text and never submits, so the submit reward
alone is 0 for every rollout and GRPO has nothing to compare; with this, a correct text answer
beats a wrong one and a correct submit (1.5 in all) beats both, so the gradient points at submit.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

from loupe.train.tasks import gym

_OPS: dict[type, Any] = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                         ast.Div: operator.truediv, ast.USub: operator.neg}  # fmt: skip


def _value(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_value(node.left), _value(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_value(node.operand))
    raise ValueError("only numbers, + - * / and parentheses")


class Calculator:
    """One reasoning-gym arithmetic problem, a calculator, and a place to submit the answer."""

    def __init__(self) -> None:
        self.task = ""
        self.entry = ""
        self.answer: str | None = None
        self.calls = 0

    def reset(self, task: str, entry: str, **_: Any) -> None:
        self.task, self.entry, self.answer, self.calls = task, entry, None, 0

    def calculate(self, expression: str) -> str:
        """Evaluate an arithmetic expression.

        Args:
            expression: Numbers, + - * / and parentheses, such as (3 + 4) * 2.

        Returns:
            The value, or why it could not be evaluated.
        """
        self.calls += 1
        try:
            value = _value(ast.parse(expression, mode="eval").body)
        except (SyntaxError, ValueError, ZeroDivisionError) as exc:
            return f"error: {exc}"
        return str(int(value)) if float(value).is_integer() else str(value)

    def submit(self, answer: str) -> str:
        """Submit the final answer; the episode is scored on the last one submitted.

        Args:
            answer: The final answer, as a number.

        Returns:
            A confirmation.
        """
        self.answer = answer
        return "submitted"

    def get_reward(self) -> float:
        """The task's own score for the submitted answer; 0 when nothing was submitted."""
        if self.answer is None:
            return 0.0
        return gym(f"<answer>{self.answer}</answer>", self.task, self.entry)


def stated(completion: str, task: str, entry: str) -> float:
    """Half the task's score for the last number in the reply's text; 0 without one."""
    numbers = re.findall(r"-?\d+(?:\.\d+)?", completion.replace(",", ""))
    if not numbers:
        return 0.0
    return 0.5 * gym(f"<answer>{numbers[-1]}</answer>", task, entry)
