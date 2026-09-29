"""Does a line of conditioning in the system prompt move how a model answers while what it answers
holds?

    uv run --all-extras python experiments/prompt-conditioning/run.py            # a local model
    uv run --all-extras python experiments/prompt-conditioning/run.py \\
        --model qwen2.5:7b-instruct --base-url http://localhost:11434/v1          # any endpoint
    uv run --all-extras python experiments/prompt-conditioning/run.py --mock     # offline wiring

The same questions, each with the context that answers it, three ways: no system line (baseline),
and each instruction in --instructions as the system prompt (by default a brief and a detailed one).
The behaviour score is the answer's length in words and should move; the correctness score is
whether the answer names the fact from the context and should hold. A verdict of `moved, held`
says the conditioning steers style without costing accuracy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.solver import generate, system_message

from loupe.grid import endpoint, grid
from loupe.inspect_ext.scorers import as_scorer
from loupe.inspect_ext.tasks import says

INSTRUCTIONS = {
    "brief": "Answer briefly. Lead with the result and leave out the reasoning unless asked.",
    "detailed": "Explain your reasoning and what you checked, not only the result.",
}

# (the context a tool or document returned, the question, the fact the answer must name)
ITEMS: list[tuple[str, str, str]] = [
    ("Calendar: Board meeting, Thursday 7pm, room 210. Game night, Friday 8pm, hall B.",
     "When's the next board meeting?", "room 210"),
    ("Budget requests: next submission due 2026-10-02. Following one due 2026-11-06.",
     "When do I have to submit the next budget request?", "2026-10-02"),
    ("Drive: 'Contact list' (sheet, drive.example/fl-1). 'Logo pack' (folder).",
     "Where is the contact list sheet?", "drive.example/fl-1"),
    ("Tasks: Sponsorship outreach, In progress, Ben and Maria. Flyer design, Not started.",
     "What's the status of sponsorship outreach?", "In progress"),
    ("Calendar: Intro to LLMs workshop, Tuesday 6pm, room 210, 40 RSVPs.",
     "How many people RSVPed to the LLM workshop?", "40"),
    ("Members: Treasurer is Priya Shah. Secretary is Ben Ortiz.",
     "Who is our treasurer?", "Priya"),
    ("Recent files: 'Workshop signup sheet' edited today. 'Budget FY26' edited Monday.",
     "Which file did we edit today?", "Workshop signup sheet"),
    ("Calendar: Room 210 is booked Wednesday 2-5pm by the robotics club.",
     "Who has room 210 on Wednesday afternoon?", "robotics"),
]  # fmt: skip


def correct(completion: str, target: str) -> float:
    """Names the fact from the context."""
    return float(says(completion, target))


def words(completion: str) -> float:
    """Length of the answer in words."""
    return float(len(completion.split()))


def questions(instruction: str | None = None, name: str = "none") -> Task:
    data = [
        Sample(id=i + 1, input=f"{ctx}\n\n{q}", target=t) for i, (ctx, q, t) in enumerate(ITEMS)
    ]
    solver = ([system_message(instruction)] if instruction else []) + [generate()]
    return Task(dataset=data, solver=solver, scorer=[as_scorer(words), as_scorer(correct)],
                name=f"conditioning-{name}")  # fmt: skip


def mocked(instructions: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Scripted stand-ins: always right, padded more the more detail is asked for."""
    pads = {"": 6, **{text: 0 if "brief" in name else 20 for name, text in instructions.items()}}

    def respond(messages, tools, tool_choice, config) -> ModelOutput:
        system = messages[0].text if messages[0].role == "system" else ""
        fact = next(t for ctx, q, t in ITEMS if messages[-1].text.endswith(q))
        text = f"{fact}." + " I checked the context for this." * (pads.get(system, 6) // 6)
        out = ModelOutput.from_content(model="mockllm/model", content=text)
        out.usage = ModelUsage(input_tokens=0, output_tokens=len(text), total_tokens=len(text))
        return out

    return {c: {"model": "mockllm/model", "custom_outputs": respond}
            for c in ["none", *instructions]}  # fmt: skip


@dataclass
class Args:
    model: str = "loupe/Qwen/Qwen2.5-0.5B-Instruct"
    """Any Inspect model; with --base-url, the id an OpenAI-compatible server serves."""
    base_url: str | None = None
    """An OpenAI-compatible server (vLLM, llama.cpp, Ollama, your own system's API)."""
    api_key: str | None = None
    """The server's key, if it checks one; never logged."""
    instructions: str = json.dumps(INSTRUCTIONS)
    """JSON: condition name to the system line it adds."""
    seeds: int = 3
    mock: bool = False
    """Scripted models in place of the model, to check the wiring offline."""


def main(args: Args) -> None:
    instructions: dict[str, str] = json.loads(args.instructions)
    target = endpoint(args.model, args.base_url, args.api_key)
    conds = mocked(instructions) if args.mock else {c: target for c in ["none", *instructions]}
    variants: dict[str, dict[str, Task | str]] = {
        name: {"questions": questions(text, name)} for name, text in instructions.items()
    }
    print(grid({"questions": questions()}, args.model, conds, "words/mean",
               seeds=list(range(args.seeds)), held="correct/mean", variants=variants,
               experiment="prompt-conditioning"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
