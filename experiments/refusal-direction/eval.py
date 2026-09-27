"""The saved refusal direction as an Inspect eval: base against ablated, on the test prompts.

    uv run --all-extras python experiments/refusal-direction/eval.py            # after run.py
    uv run --all-extras python experiments/refusal-direction/eval.py --tiny

The ablated run goes through the loupe/ provider with the direction as a model arg, the way any
Inspect task can be run under an intervention. Open the two runs in Compare.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import tyro
from inspect_ai import Task, eval, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import grouped, mean
from inspect_ai.solver import generate

sys.path.insert(0, str(Path(__file__).parent))
from run import Args as RunArgs
from run import data

from loupe.core import logs_dir
from loupe.inspect_ext import refusal


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    tiny: bool = False
    """Evaluate the planted toy that `run.py --tiny` saved."""
    vector: str | None = None
    """Defaults to the name run.py saved the direction under."""
    n_test: int = 32
    max_tokens: int = 48
    seed: int = 0


@task
def refusal_direction(condition: str, prompts: dict[str, list[str]], max_tokens: int) -> Task:
    samples = [
        Sample(id=f"{kind}-{i + 1}", input=p, target=kind, metadata={"kind": kind})
        for kind in ("harmful", "harmless")
        for i, p in enumerate(prompts[f"{kind}_test"])
    ]
    return Task(
        display_name=f"refusal eval · {condition}",
        dataset=samples,
        solver=generate(),
        scorer=refusal(),
        metrics=[grouped(mean(), "kind")],
        config=GenerateConfig(temperature=0, max_tokens=max_tokens),
    )


def main(args: Args) -> None:
    name = "tiny-planted-refusal" if args.tiny else args.model
    vector = args.vector or "refusal." + name.split("/")[-1].lower()
    prompts = data(RunArgs(tiny=args.tiny, n_test=args.n_test, seed=args.seed))
    conditions = {
        "base": None,
        "ablated": {"kind": "ablate", "vector": vector},
    }
    for condition, spec in conditions.items():
        model = get_model(f"loupe/{name}", interventions=spec)
        eval(
            refusal_direction(condition, prompts, args.max_tokens),
            model=model,
            log_dir=str(logs_dir()),
            tags=["experiment:refusal-direction", f"condition:{condition}"],
            metadata={"condition": condition, "interventions": spec},
            display="none",
        )


if __name__ == "__main__":
    main(tyro.cli(Args))
