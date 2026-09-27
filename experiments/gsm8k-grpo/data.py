"""GSM8K as GRPO prompts: {"prompt": [messages], "answer": "<number>"} rows under LOUPE_HOME.

uv run --all-extras python experiments/gsm8k-grpo/data.py
"""

from __future__ import annotations

import json

from datasets import load_dataset

from loupe.core import home

INSTRUCTION = "Solve the problem. End with the final answer as a number."


def rows(split: str) -> list[dict]:
    out = []
    for row in load_dataset("openai/gsm8k", "main", split=split):
        answer = row["answer"].split("####")[-1].strip()
        prompt = [{"role": "system", "content": INSTRUCTION},
                  {"role": "user", "content": row["question"]}]  # fmt: skip
        out.append({"prompt": prompt, "answer": answer})
    return out


if __name__ == "__main__":
    folder = home() / "data" / "gsm8k-grpo"
    folder.mkdir(parents=True, exist_ok=True)
    for split in ("train", "test"):
        (folder / f"{split}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows(split)))
    print(folder)
