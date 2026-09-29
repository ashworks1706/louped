"""Does a line of conditioning in the system prompt move how a model answers while what it answers
holds?

    uv run --all-extras python experiments/prompt-conditioning/run.py            # a local model
    uv run --all-extras python experiments/prompt-conditioning/run.py \\
        --model qwen2.5:7b-instruct --base-url http://localhost:11434/v1          # any endpoint

The same questions, each with the context that answers it, three ways: no system line (baseline),
and each instruction in --instructions as the system prompt (by default a brief and a detailed one).
The behaviour score is the answer's length in words and should move; the correctness score is
whether the answer names the fact from the context and should hold. A verdict of `moved, held`
says the conditioning steers style without costing accuracy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import tyro
from inspect_ai import Task
from inspect_ai.dataset import Sample
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
    ("Timetable: the 7:40 train to Leeds leaves from platform 4; the 8:10 from platform 2.",
     "Which platform does the 7:40 leave from?", "4"),
    ("Invoice 3318: 12 units at 45.00 each, due 2026-11-02, paid by bank transfer.",
     "When is invoice 3318 due?", "2026-11-02"),
    ("Recipe: bake the bread at 220 C for 35 minutes, then rest it for 10.",
     "How long does the bread bake?", "35 minutes"),
    ("Lab log: sample B7 was stored at -80 C in freezer 3, shelf 2.",
     "Which freezer holds sample B7?", "freezer 3"),
    ("Release notes: version 2.4 adds offline mode and drops support for Python 3.9.",
     "Which Python version does 2.4 drop?", "3.9"),
    ("Roster: the night shift on Friday is covered by Amara Osei; Saturday by Jon Keller.",
     "Who covers the Friday night shift?", "Amara"),
    ("Weather: tomorrow 14 C, rain after 3pm, wind from the north-west at 20 km/h.",
     "When does the rain start tomorrow?", "3pm"),
    ("Library record: 'The Left Hand of Darkness' is on shelf F-12, due back on the 18th.",
     "Which shelf is the book on?", "F-12"),
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


def main(args: Args) -> None:
    instructions: dict[str, str] = json.loads(args.instructions)
    target = endpoint(args.model, args.base_url, args.api_key)
    conds = {c: target for c in ["none", *instructions]}
    variants: dict[str, dict[str, Task | str]] = {
        name: {"questions": questions(text, name)} for name, text in instructions.items()
    }
    print(grid({"questions": questions()}, args.model, conds, "words/mean",
               seeds=list(range(args.seeds)), held="correct/mean", variants=variants,
               experiment="prompt-conditioning"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
