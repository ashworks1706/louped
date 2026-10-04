"""Scorers over an agent's tool calls, on a scripted mock model through Inspect's react agent."""

from __future__ import annotations

from inspect_ai import Task, eval
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.tool import ToolError, tool

from louped.inspect_ext import called, grounded, tool_calls, tool_errors


@tool
def lookup():
    async def execute(key: str) -> str:
        """Look up a key.

        Args:
            key: The key.
        """
        if key != "answer":
            raise ToolError(f"no key {key}")
        return "42\n"

    return execute


def scripted(calls: list[tuple[str, dict]]):
    """A mock model that makes the given tool calls in order, one per turn."""
    script = iter(calls)

    def respond(messages, tools, tool_choice, config) -> ModelOutput:
        name, arguments = next(script)
        out = ModelOutput.for_tool_call("mockllm/model", name, arguments)
        out.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
        return out

    return respond


def run(calls: list[tuple[str, dict]]) -> dict[str, float]:
    task = Task(
        dataset=[Sample(input="What is the answer?", target="42")],
        solver=react(tools=[lookup()], attempts=1),
        scorer=[tool_calls(), tool_errors(), called("lookup"), grounded("lookup")],
    )
    model = get_model("mockllm/model", custom_outputs=scripted(calls))
    [log] = eval(task, model=model, display="none", log_dir="logs-unused")
    assert log.status == "success" and log.samples
    scores = log.samples[0].scores or {}
    return {name: float(s.as_float()) for name, s in scores.items()}


def test_tool_scorers_count_errors_and_ground_the_answer(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    scores = run([("lookup", {"key": "nope"}), ("lookup", {"key": "answer"}),
                  ("submit", {"answer": "The answer is 42."})])  # fmt: skip
    assert scores == {"tool_calls": 2, "tool_errors": 0.5, "called": 1, "grounded": 1}


def test_an_answer_without_the_tool_is_ungrounded(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    scores = run([("submit", {"answer": "The answer is 7."})])
    assert scores == {"tool_calls": 0, "tool_errors": 0, "called": 0, "grounded": 0}
