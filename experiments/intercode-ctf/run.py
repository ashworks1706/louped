"""InterCode-CTF from inspect_evals (gdm_intercode_ctf) through the loupe/ provider: a react agent
with bash and python in a Docker sandbox per sample, base and optionally under an intervention, as
one grid with the paired difference per sample.

    uv run --all-extras python experiments/intercode-ctf/run.py --limit 5    # a smoke run
    uv run --all-extras python experiments/intercode-ctf/run.py              # all 78 tasks
    uv run --all-extras python experiments/intercode-ctf/run.py \\
        --intervention '{"kind": "steer", "vector": "<a saved vector>", "alpha": 4}'
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from typing import Any

import tyro
from inspect_ai import task_with
from inspect_ai.model import GenerateConfig
from inspect_evals.constants import INSPECT_EVALS_CACHE_PATH
from inspect_evals.gdm_intercode_ctf import gdm_intercode_ctf

from loupe.grid import grid


@dataclass
class Args:
    model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    revision: str | None = None
    """The model's Hub commit, for a result that reruns on the same weights."""
    intervention: str | None = None
    """An intervention spec as JSON, run beside the base."""
    limit: int | None = None
    """Tasks of the 78 that need no internet; None is all of them."""
    max_tokens: int = 1024
    """Per model turn: a tool call must fit whole or it does not parse."""
    max_attempts: int = 3
    max_messages: int = 50


def main(args: Args) -> None:
    pin = {"revision": args.revision} if args.revision else {}
    conditions: dict[str, dict[str, Any]] = {"base": pin}
    if args.intervention:
        conditions["intervened"] = {**pin, "interventions": json.loads(args.intervention)}
    # inspect_evals renames its download from a temp dir into its cache, which fails when /tmp is
    # another filesystem (tmpfs); keep the download's temp dir on the cache's
    INSPECT_EVALS_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(INSPECT_EVALS_CACHE_PATH)
    try:
        task = gdm_intercode_ctf(max_attempts=args.max_attempts, max_messages=args.max_messages)
    finally:
        tempfile.tempdir = None
    dataset = task.dataset[: args.limit] if args.limit else task.dataset
    task = task_with(task, dataset=dataset,
                     config=GenerateConfig(max_tokens=args.max_tokens, temperature=0))  # fmt: skip
    run = grid({"intercode-ctf": task}, args.model, conditions, "includes/accuracy",
               experiment="intercode-ctf")  # fmt: skip
    print(json.dumps({"grid": run}))


if __name__ == "__main__":
    main(tyro.cli(Args))
