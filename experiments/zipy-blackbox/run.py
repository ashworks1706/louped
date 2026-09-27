"""Does zipy's text conditioning move how its chat model answers while what it answers holds?

    uv run python experiments/zipy-blackbox/run.py          # zipy's model server up
    uv run python experiments/zipy-blackbox/run.py --mock   # offline wiring check

zipy conditions its chat model on a member's collaboration state as lines in the system prompt
(conditioning = "text" in zipy.toml). This asks the same questions of the same endpoint with no
such line, with the brief end of its depth dimension, and with the detailed end. The behaviour
score is the answer's length in words and must move; the correctness score is whether the answer
names the fact from the context and must hold.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.solver import generate, system_message

from loupe.grid import grid
from loupe.inspect_ext.scorers import as_scorer
from loupe.inspect_ext.tasks import says

# The depth dimension's two ends, worded as in zipy's apps/engine/cognition/conditioning/text.py.
CONDITIONING = {
    "brief": "Answer briefly. Lead with the result and leave out the reasoning unless asked.",
    "detailed": "Explain your reasoning and what you checked, not only the result.",
}

# (what the org's tools returned, the member's question, the fact the answer must name)
ITEMS: list[tuple[str, str, str]] = [
    ("Calendar: Exec board meeting, Thursday 7pm, CPCOM 210. Game night, Friday 8pm, MU 230.",
     "When's the next exec board meeting?", "CPCOM 210"),
    ("Notion Budget requests: next submission due 2026-10-02. Following one due 2026-11-06.",
     "When do I have to submit the next budget request?", "2026-10-02"),
    ("Drive: 'Officer contact list' (sheet, drive.example/fl-1). 'Logo pack' (folder).",
     "Where is the officer contact list sheet?", "drive.example/fl-1"),
    ("Notion Tasks: Sponsorship outreach, In progress, Ben and Maria. Flyer design, Not started.",
     "What's the status of sponsorship outreach?", "In progress"),
    ("Calendar: Intro to LLMs workshop, Tuesday 6pm, room CPCOM 210, 40 RSVPs.",
     "How many people RSVPed to the LLM workshop?", "40"),
    ("Notion Members: Treasurer is Priya Shah. Secretary is Ben Ortiz.",
     "Who is our treasurer?", "Priya"),
    ("Drive recent: 'Workshop signup sheet' edited today. 'Budget FY26' edited Monday.",
     "Which file did we edit today?", "Workshop signup sheet"),
    ("Calendar: Room CPCOM 210 is booked Wednesday 2-5pm by the robotics club.",
     "Who has CPCOM 210 on Wednesday afternoon?", "robotics"),
]  # fmt: skip


def correct(completion: str, target: str) -> float:
    """Names the fact from the context."""
    return float(says(completion, target))


def words(completion: str) -> float:
    """Length of the answer in words."""
    return float(len(completion.split()))


def org(condition: str | None = None) -> Task:
    data = [
        Sample(id=i + 1, input=f"{ctx}\n\n{q}", target=t) for i, (ctx, q, t) in enumerate(ITEMS)
    ]
    solver = ([system_message(CONDITIONING[condition])] if condition else []) + [generate()]
    return Task(dataset=data, solver=solver, scorer=[as_scorer(words), as_scorer(correct)],
                name=f"zipy-org-{condition or 'none'}")  # fmt: skip


def mocked(names: list[str]) -> dict[str, dict[str, Any]]:
    """Scripted stand-ins: always right, padded more the more detail is asked for."""

    def respond(messages, tools, tool_choice, config) -> ModelOutput:
        system = messages[0].text if messages[0].role == "system" else ""
        fact = next(t for ctx, q, t in ITEMS if messages[-1].text.endswith(q))
        pad = {"": 6, CONDITIONING["brief"]: 0, CONDITIONING["detailed"]: 20}[system]
        text = f"{fact}." + " I checked the context for this." * (pad // 6)
        out = ModelOutput.from_content(model="mockllm/model", content=text)
        out.usage = ModelUsage(input_tokens=0, output_tokens=len(text), total_tokens=len(text))
        return out

    return {c: {"model": "mockllm/model", "custom_outputs": respond} for c in names}


@dataclass
class Args:
    mock: bool = False
    """Scripted models in place of the endpoint, to check the wiring offline."""
    seeds: int = 3


def main(args: Args) -> None:
    # Inspect reads ZIPY_BASE_URL and ZIPY_API_KEY; zipy.toml's chat role is this server.
    os.environ.setdefault("ZIPY_BASE_URL", "http://127.0.0.1:8000/v1")
    os.environ.setdefault("ZIPY_API_KEY", "local")
    names = ["none", *CONDITIONING]
    conds: dict[str, dict[str, Any]] = {c: {"model": "openai-api/zipy/zipy-chat"} for c in names}
    if args.mock:
        conds = mocked(names)
    variants: dict[str, dict[str, Task | str]] = {c: {"org": org(c)} for c in CONDITIONING}
    print(grid({"org": org()}, "zipy-chat", conds, "words/mean", seeds=list(range(args.seeds)),
               held="correct/mean", variants=variants, experiment="zipy-blackbox"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
