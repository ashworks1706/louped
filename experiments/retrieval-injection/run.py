"""How much does a model gain from retrieved passages placed in its prompt, and does injecting the
same passages into its residual stream, with no prompt text, reach that gain?

    uv run --all-extras python experiments/retrieval-injection/run.py --inject-layer 12
    uv run --all-extras python experiments/retrieval-injection/run.py \
        --model qwen2.5:7b-instruct --base-url http://localhost:11434/v1     # prompted, any server
    uv run --all-extras python experiments/retrieval-injection/run.py --mock    # offline wiring

BM25 over the passages below puts the top k in the prompt (loupe.inspect_ext.rag); the baseline is
the same questions closed book. The passages describe a made-up station, so the answers are not in
the weights. With --inject-layer, a third condition runs the checkpoint locally through the loupe
provider with the passages injected at that layer instead of prompted: retrieval inside the model,
on the same weights. The closed and prompted conditions run on --model, a local model or any
OpenAI-compatible endpoint (a serving stack with its own retrieval, say); inject needs the weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import Task
from inspect_ai.model import ModelOutput, ModelUsage

from loupe.grid import endpoint, grid
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
    model: str = "loupe/Qwen/Qwen2.5-0.5B-Instruct"
    """For closed book and prompted: any Inspect model, or with --base-url a served id."""
    base_url: str | None = None
    """An OpenAI-compatible server for closed book and prompted."""
    api_key: str | None = None
    """The server's key, if it checks one; never logged."""
    k: int = 2
    """Passages placed in the prompt."""
    inject_layer: int | None = None
    """Also run the checkpoint locally with the passages injected at this layer."""
    checkpoint: str | None = None
    """The Hugging Face id for the inject condition; by default --model's, when it is loupe/<id>."""
    mock: bool = False
    """Scripted models in place of the endpoint, to check the wiring offline."""
    seeds: int = 1


def main(args: Args) -> None:
    index = Index(PASSAGES)
    served = endpoint(args.model, args.base_url, args.api_key)
    conds: dict[str, dict[str, Any]] = {"closed": served, "rag": served}
    variants: dict[str, dict[str, Task | str]] = {
        "rag": {"kestrel": rag(ITEMS, index, k=args.k, mode="bm25", name="kestrel-rag")}
    }
    if args.inject_layer is not None:
        checkpoint = args.checkpoint or args.model.removeprefix("loupe/")
        if checkpoint == args.model:
            raise SystemExit("--inject-layer needs --checkpoint: the weights of the served model")
        conds["inject"] = {"model": f"loupe/{checkpoint}",
                           "inject": {"layer": args.inject_layer}}  # fmt: skip
        variants["inject"] = {"kestrel": rag(ITEMS, index, k=args.k, mode="bm25", into="state",
                                             name="kestrel-inject")}  # fmt: skip
    if args.mock:
        conds = mocked(list(conds))
    closed = rag(ITEMS, index, k=0, name="kestrel-closed")
    print(grid({"kestrel": closed}, args.model, conds, "f1/mean", seeds=list(range(args.seeds)),
               variants=variants, experiment="retrieval-injection"))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
