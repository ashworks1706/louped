"""reasoning-gym arithmetic as GRPO rows under LOUPE_HOME; generated offline, any size.

uv run --all-extras python experiments/tool-rl/data.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import tyro

from loupe.core import home
from loupe.train.tasks import gym_rows

INSTRUCTION = "Use the calculate tool for arithmetic, then call submit with the final answer."


@dataclass
class Args:
    task: str = "basic_arithmetic"
    train: int = 2000
    test: int = 200


def rows(task: str, size: int, seed: int) -> list[dict]:
    out = gym_rows(task, size, seed)
    for row in out:
        row["prompt"][0]["content"] = INSTRUCTION
    return out


def main(args: Args) -> None:
    folder = home() / "data" / "tool-rl"
    folder.mkdir(parents=True, exist_ok=True)
    for split, size, seed in (("train", args.train, 0), ("test", args.test, 1)):
        lines = "".join(json.dumps(r) + "\n" for r in rows(args.task, size, seed))
        (folder / f"{split}.jsonl").write_text(lines)
    print(folder)


if __name__ == "__main__":
    main(tyro.cli(Args))
