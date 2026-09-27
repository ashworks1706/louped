"""inspect_evals GSM8K through the loupe/ provider: base against the reported number, and the same
task under an intervention, as one grid with the paired difference per sample.

    uv run --all-extras python experiments/inspect-evals-baseline/run.py
    uv run --all-extras python experiments/inspect-evals-baseline/run.py --limit 50   # a smoke run

The default intervention ablates the direction experiments/refusal-direction saved for the model,
so run that first, or pass another spec with --intervention (or `--intervention None`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import task_with
from inspect_ai.model import GenerateConfig
from inspect_evals.gsm8k import gsm8k

from loupe import stores
from loupe.grid import grid

#: GSM8K accuracy of the instruct models in the Qwen2.5 release (qwenlm.github.io/blog/qwen2.5-llm,
#: "Qwen2.5-0.5B/1.5B-Instruct Performance"; the same numbers in arXiv:2412.15115).
REPORTED = {"Qwen/Qwen2.5-0.5B-Instruct": 0.496, "Qwen/Qwen2.5-1.5B-Instruct": 0.732}


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    revision: str | None = None
    """The model's Hub commit; pin it so the comparison with the reported number reruns."""
    intervention: str | None = '{"kind": "ablate", "vector": "refusal.qwen2.5-0.5b-instruct"}'
    """An intervention spec as JSON for the second run; None runs the base only."""
    fewshot: int = 10
    """inspect_evals' default; its examples also show the ANSWER: line the scorer reads."""
    limit: int | None = None
    """Samples of the 1319 in the test split; None is all of them."""
    max_tokens: int = 512


def main(args: Args) -> None:
    pin = {"revision": args.revision} if args.revision else {}
    conditions: dict[str, dict[str, Any]] = {"base": pin}
    if args.intervention:
        conditions["intervened"] = {**pin, "interventions": json.loads(args.intervention)}
    task = gsm8k(fewshot=args.fewshot)
    dataset = task.dataset[: args.limit] if args.limit else task.dataset
    task = task_with(task, dataset=dataset,
                     config=GenerateConfig(max_tokens=args.max_tokens, temperature=0))  # fmt: skip
    run = grid({"gsm8k": task}, args.model, conditions, "match/accuracy",
               experiment="inspect-evals-baseline")  # fmt: skip
    reported = REPORTED.get(args.model)
    cells = stores.list_views(run)[-1].view.model_dump()["rows"]
    for condition, _, _, _, _, eval_run in cells:
        metrics = stores.get_run(eval_run).metrics
        accuracy, stderr = metrics.get("match/accuracy"), metrics.get("match/stderr")
        within = None
        if reported is not None and accuracy is not None and stderr is not None:
            within = abs(accuracy - reported) <= 1.96 * stderr
        print(json.dumps({"grid": run, "run": eval_run, "condition": condition,
                          "accuracy": accuracy, "stderr": stderr, "reported": reported,
                          "within_95pct_of_reported": within}))  # fmt: skip


if __name__ == "__main__":
    main(tyro.cli(Args))
