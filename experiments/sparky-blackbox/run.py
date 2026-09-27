"""Does SparkyAI's agent answer ASU questions better than the model it runs on, and decline what it
cannot know?

    uv run python experiments/sparky-blackbox/run.py          # engine and model up
    uv run python experiments/sparky-blackbox/run.py --mock   # offline wiring check

Two conditions on the same questions, both reached as OpenAI-compatible endpoints: the bare chat
model on SparkyAI's llama-server (baseline) and the engine, whose /v1/chat/completions runs the
whole agent (retrieval, live search, tools) and answers as the model "sparky". Each answerable
question is scored on naming a gold answer; each unanswerable one on declining. The engine's
appended Tools and Sources blocks are cut before scoring, so a citation cannot answer for it.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage
from inspect_ai.solver import generate

from loupe.grid import grid
from loupe.inspect_ext.scorers import as_scorer, is_refusal
from loupe.inspect_ext.tasks import says

# (question, gold answers); no answers means the question cannot be answered and should be declined.
ITEMS: list[tuple[str, list[str]]] = [
    ("What is the name of ASU's mascot?", ["Sparky"]),
    ("What are ASU's school colors?", ["maroon"]),
    ("In which city is ASU's main campus, where Hayden Library is?", ["Tempe"]),
    ("What is the ASU student ID card called?", ["Sun Card", "SunCard"]),
    ("Which learning management system do ASU courses use?", ["Canvas"]),
    ("Which app does ASU use for two-factor sign-in?", ["Duo"]),
    ("What is ASU's student web portal called?", ["My ASU", "MyASU"]),
    ("What is the name of ASU's honors college?", ["Barrett"]),
    ("Which ASU campus is in Mesa?", ["Polytechnic"]),
    ("Which athletic conference do ASU's teams play in?", ["Big 12"]),
    ("What is my current GPA?", []),
    ("What is the office phone number of the Tempe campus dentist?", []),
    ("What did my roommate have for breakfast today?", []),
]

DECLINES = ("don't know", "do not know", "don't have", "do not have", "not sure", "couldn't find",
            "could not find", "no information", "not able to", "no access")  # fmt: skip


def correct(completion: str, answers: list[str]) -> float:
    """Names a gold answer, or for a question with none, declines."""
    text = completion.split("\n\nTools:")[0].split("\n\nSources")[0]
    if not answers:
        return float(is_refusal(text) or any(d in text.lower() for d in DECLINES))
    return float(says(text, answers))


def asu() -> Task:
    data = [Sample(id=i + 1, input=q, metadata={"answers": a}) for i, (q, a) in enumerate(ITEMS)]
    return Task(dataset=data, solver=[generate()], scorer=as_scorer(correct), name="asu-questions")


def conditions() -> dict[str, dict[str, Any]]:
    # Inspect reads <SERVICE>_BASE_URL and <SERVICE>_API_KEY; keys stay out of the logged args.
    os.environ.setdefault("LLAMA_BASE_URL", "http://localhost:8000/v1")
    os.environ.setdefault("LLAMA_API_KEY", "local")
    os.environ.setdefault("SPARKY_BASE_URL", "http://localhost:8080/v1")
    os.environ.setdefault("SPARKY_API_KEY", "change-me")
    # The engine keys conversation and memory by user; a fresh one per run starts clean.
    user = f"loupe-{uuid.uuid4().hex[:8]}"
    return {
        "model": {"model": "openai-api/llama/sparky-chat"},
        "engine": {"model": "openai-api/sparky/sparky",
                   "config": GenerateConfig(extra_body={"user": user})},
    }  # fmt: skip


def mocked(names: list[str]) -> dict[str, dict[str, Any]]:
    """Scripted stand-ins: the model knows the first half, the engine all but one."""
    known = {"model": len(ITEMS) // 2, "engine": len(ITEMS) - 1}
    gold = {q: (i, a) for i, (q, a) in enumerate(ITEMS)}

    def outputs(n: int):
        def respond(messages, tools, tool_choice, config) -> ModelOutput:
            i, answers = gold[messages[-1].text]
            ok = i < n
            text = answers[0] if answers and ok else "I don't know." if ok else "It is Phoenix."
            out = ModelOutput.from_content(
                model="mockllm/model", content=f"{text}\n\nSources\n1. x"
            )
            out.usage = ModelUsage(input_tokens=0, output_tokens=len(text), total_tokens=len(text))
            return out

        return respond

    return {c: {"model": "mockllm/model", "custom_outputs": outputs(known[c])} for c in names}


@dataclass
class Args:
    mock: bool = False
    """Scripted models in place of the endpoints, to check the wiring offline."""
    seeds: int = 1


def main(args: Args) -> None:
    conds = conditions()
    if args.mock:
        conds = mocked(list(conds))
    print(grid({"asu": asu()}, "sparky", conds, "correct/mean", seeds=list(range(args.seeds)),
               experiment="sparky-blackbox"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
