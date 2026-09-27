"""How much does the model piramid serves gain from passages placed in the prompt, the plain-RAG
baseline that piramid's retrieval during generation has to beat?

    uv run --extra rag python experiments/piramid-blackbox/run.py          # piramid up
    uv run --extra rag python experiments/piramid-blackbox/run.py --mock   # offline check

piramid's /v1/chat/completions serves its loaded model without retrieval, so retrieval happens
here: BM25 over the passages below, the top k placed in the prompt (loupe.inspect_ext.rag). The
baseline is the same questions closed book. The passages describe a made-up station, so the
answers are not in the weights. With --inject-layer, a third condition runs the same checkpoint
locally through the loupe provider with the passages injected at that layer instead of prompted:
retrieval inside the model, on the same weights.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import Task
from inspect_ai.model import ModelOutput, ModelUsage

from loupe.grid import grid
from loupe.inspect_ext.rag import rag
from loupe.retrieval import Index

PASSAGES = {
    "site": "Kestrel Station is a research outpost on the Varn Plateau, 2,140 metres up.",
    "crew": "Kestrel Station has a winter crew of nine, led by station chief Odile Marsh.",
    "power": "Kestrel Station runs on three wind turbines and a backup methanol generator.",
    "supply": "Supply flights reach Kestrel Station every eleven days from the town of Ferrow.",
    "radio": "The station radio listens on 7.415 MHz; the call sign is KSX-4.",
    "lab": "The Kestrel lab studies lichen growth rates under ultraviolet exposure.",
    "water": "Drinking water comes from snowmelt filtered through a ceramic bed.",
    "founded": "Kestrel Station was founded in 1987 by the Aurel Polar Institute.",
}

# (question, gold answers, gold passage ids)
ITEMS: list[tuple[str, list[str], list[str]]] = [
    ("Who leads the winter crew at Kestrel Station?", ["Odile Marsh"], ["crew"]),
    ("How often do supply flights reach Kestrel Station?", ["every eleven days"], ["supply"]),
    ("What is the Kestrel Station radio call sign?", ["KSX-4"], ["radio"]),
    ("Which institute founded Kestrel Station?", ["Aurel Polar Institute"], ["founded"]),
    ("On which plateau is Kestrel Station?", ["Varn Plateau"], ["site"]),
    ("What does the Kestrel lab study?", ["lichen growth rates"], ["lab"]),
    ("What is the backup power source at Kestrel Station?", ["methanol generator"], ["power"]),
    ("Where do supply flights to Kestrel Station come from?", ["Ferrow"], ["supply"]),
]


def mocked(names: list[str]) -> dict[str, dict[str, Any]]:
    """Scripted stand-ins: answers when a gold passage reached it, guesses otherwise."""
    gold = [(q, PASSAGES[ids[0]], answers[0]) for q, answers, ids in ITEMS]

    def respond(messages, tools, tool_choice, config) -> ModelOutput:
        seen = " ".join(m.text for m in messages)
        text = next((a for q, p, a in gold if q in seen and p in seen), "I am not sure.")
        out = ModelOutput.from_content(model="mockllm/model", content=text)
        out.usage = ModelUsage(input_tokens=0, output_tokens=len(text), total_tokens=len(text))
        return out

    return {c: {"model": "mockllm/model", "custom_outputs": respond} for c in names}


@dataclass
class Args:
    served: str = "Qwen2.5-0.5B-Instruct"
    """The model id piramid answers to: inference.model_name, else the model_path directory name."""
    k: int = 2
    """Passages placed in the prompt."""
    inject_layer: int | None = None
    """Also run the same checkpoint locally with the passages injected at this layer."""
    checkpoint: str = "Qwen/Qwen2.5-0.5B-Instruct"
    """The Hugging Face id of the checkpoint piramid serves, for the inject condition."""
    mock: bool = False
    """Scripted models in place of the endpoint, to check the wiring offline."""
    seeds: int = 1


def main(args: Args) -> None:
    # Inspect reads PIRAMID_BASE_URL and PIRAMID_API_KEY, the key piramid serve checks when set.
    os.environ.setdefault("PIRAMID_BASE_URL", "http://127.0.0.1:6333/v1")
    os.environ.setdefault("PIRAMID_API_KEY", "unused")
    index = Index(PASSAGES)
    served = {"model": f"openai-api/piramid/{args.served}"}
    conds: dict[str, dict[str, Any]] = {"closed": served, "rag": served}
    variants: dict[str, dict[str, Task | str]] = {
        "rag": {"kestrel": rag(ITEMS, index, k=args.k, mode="bm25", name="kestrel-rag")}
    }
    if args.inject_layer is not None:
        conds["inject"] = {"model": f"loupe/{args.checkpoint}",
                           "inject": {"layer": args.inject_layer}}  # fmt: skip
        variants["inject"] = {"kestrel": rag(ITEMS, index, k=args.k, mode="bm25", into="state",
                                             name="kestrel-inject")}  # fmt: skip
    if args.mock:
        conds = mocked(list(conds))
    closed = rag(ITEMS, index, k=0, name="kestrel-closed")
    print(grid({"kestrel": closed}, args.served, conds, "f1/mean", seeds=list(range(args.seeds)),
               variants=variants, experiment="piramid-blackbox"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
