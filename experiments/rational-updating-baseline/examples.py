"""Items from a finished `sru run` to read by hand, written to <run>/examples.md.

Runs in the harness's environment (it imports sru), never loupe's:

    .loupe/vendor/sru-venv/bin/python experiments/rational-updating-baseline/examples.py RUN_DIR

Each item shows the question, the model's first-turn answer, the second-turn message, the
final answer and how it was scored, rebuilt with the harness's own conversation builder so the
text is what the model saw. Picks, in order and seeded: yielded (right, then wrong under
pressure), updated (wrong, then right after evidence or user evidence), held (right, stayed
right under pressure), not updated (wrong, stayed wrong after evidence).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from sru.datasets import load_rows
from sru.pipeline import RunConfig, build_conversation, load_records
from sru.prompts import build_popqa_pool

QUOTAS = {"yielded": 3, "updated": 3, "held": 2, "not updated": 2}


def picks(rec: dict[str, dict[int, dict]], n: int, seed: int) -> list[tuple[str, str, int]]:
    base = rec["baseline"]
    pools: dict[str, list[tuple[str, int]]] = {k: [] for k in QUOTAS}
    for qid, b in sorted(base.items()):
        if b["correct"] and qid in rec.get("pressure", {}):
            kind = "held" if rec["pressure"][qid]["correct"] else "yielded"
            pools[kind].append(("pressure", qid))
        for cond in ("evidence", "user_evidence"):
            if not b["correct"] and qid in rec.get(cond, {}):
                kind = "updated" if rec[cond][qid]["correct"] else "not updated"
                pools[kind].append((cond, qid))
    rng = random.Random(seed)
    for pool in pools.values():
        rng.shuffle(pool)
    rest = [(k, c, q) for k, pool in pools.items() for c, q in pool]
    rng.shuffle(rest)
    ordered = [(k, *pools[k][i]) for k, q in QUOTAS.items() for i in range(min(q, len(pools[k])))]
    out, seen = [], set()
    for kind, cond, qid in ordered + rest:  # one condition per item, so n distinct questions
        if qid not in seen and len(out) < n:
            seen.add(qid)
            out.append((kind, cond, qid))
    return out


def answer(dataset: str, row: dict, r: dict) -> str:
    if dataset != "truthfulqa" or "response" in r:
        return r.get("response", r.get("first_turn_text", ""))
    choices = row["mc1_targets"]["choices"]
    return choices[r["pred"]]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", type=Path)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    raw = json.loads((a.run_dir / "config.json").read_text())
    config = RunConfig(**{**raw, "out_dir": Path(raw["out_dir"]),
                          "datasets": tuple(raw["datasets"]),
                          "conditions": tuple(raw["conditions"])})  # fmt: skip
    lines = [f"# Examples to read: {config.model}, {config.split}",
             "", "Fill in the verdict line for each item: is the score right, and is the move "
             "(or the hold) appropriate given the second turn?", ""]  # fmt: skip
    for dataset in config.datasets:
        rows = {int(r["qid"]): r for r in load_rows(dataset, config.split, config.limit)}
        pool = build_popqa_pool(list(rows.values())) if dataset == "popqa" else None
        rec = {c: load_records(a.run_dir / "raw" / dataset / f"{c}.jsonl")
               for c in ("baseline", *config.conditions)}  # fmt: skip
        for i, (kind, cond, qid) in enumerate(picks(rec, a.n, a.seed), 1):
            row, b, r = rows[qid], rec["baseline"][qid], rec[cond][qid]
            messages, _ = build_conversation(config, dataset, row, cond,
                                             b.get("first_turn_text"), pool)  # fmt: skip
            lines += [f"## {i}. {dataset} qid {qid}: {kind} ({cond})", ""]
            lines += [f"**Turn 1 (user)**\n\n```\n{messages[0]['content']}\n```", ""]
            lines += [f"**Turn 1 (model)**, correct={b['correct']}\n\n```\n"
                      f"{b.get('first_turn_text', '')}\n```", ""]  # fmt: skip
            lines += [f"**Turn 2 (user)**\n\n```\n{messages[-1]['content']}\n```", ""]
            lines += [f"**Turn 2 (model)**, pred={r['pred']!r} gold={r['gold']!r} "
                      f"correct={r['correct']} abstain={r['abstain']}\n\n```\n"
                      f"{answer(dataset, row, r)}\n```", ""]  # fmt: skip
            if "scores" in r:  # TruthfulQA has at least two options
                top = sorted(r["scores"], reverse=True)
                lines += [f"Option scores (mean token logprob): {r['scores']}; "
                          f"top-two margin {top[0] - top[1]:.4f}", ""]  # fmt: skip
            lines += ["Verdict: ", ""]
    (a.run_dir / "examples.md").write_text("\n".join(lines))
    print(f"wrote {a.run_dir / 'examples.md'}")


if __name__ == "__main__":
    main()
