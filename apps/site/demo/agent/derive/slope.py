"""Each item's slope as a column on Items: how far adding the vector moves P(agree), per unit of
multiplier, from subtract (-1) to add (+1). Below zero, the item moves against the vector."""

import json
from pathlib import Path


def derive(files: Path) -> list[dict]:
    def p_agree(condition: str) -> dict[str, float]:
        lines = (files / "ab" / f"{condition}.jsonl").read_text().splitlines()
        return {r["qid"]: r["p_agree"] for r in map(json.loads, lines)}

    add, subtract = p_agree("add"), p_agree("subtract")
    return [{"qid": q, "slope": round((add[q] - subtract[q]) / 2, 3)} for q in add]
