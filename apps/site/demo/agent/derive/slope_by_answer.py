"""Each item's slope by which answer agrees with the user, as a chart on Figures: if the vector
moved only agreement, (A) and (B) items would sit alike above zero."""

import json
from pathlib import Path

from louped.analysis import views


def derive(files: Path) -> dict:
    def rows(condition: str) -> list[dict]:
        lines = (files / "ab" / f"{condition}.jsonl").read_text().splitlines()
        return [json.loads(line) for line in lines]

    subtract = {r["qid"]: r["p_agree"] for r in rows("subtract")}
    values = [
        {"qid": r["qid"], "agreeing": f"({r['agreeing']})",
         "slope": round((r["p_agree"] - subtract[r["qid"]]) / 2, 3)}
        for r in rows("add")
    ]  # fmt: skip
    spec = {
        "data": {"values": values},
        "encoding": {
            "x": {"field": "agreeing", "type": "nominal", "title": "agreeing answer"},
            "y": {"field": "slope", "type": "quantitative"},
            "color": {"field": "agreeing", "type": "nominal", "legend": None},
        },
        "layer": [
            {"mark": {"type": "boxplot", "extent": "min-max", "opacity": 0.25, "size": 60}},
            {"mark": {"type": "point", "filled": True, "opacity": 0.7, "size": 50}},
        ],
    }
    return views.vega(
        "Slope by agreeing answer",
        spec,
        about="Each point is one item. Below zero, adding the vector makes agreeing less likely.",
        items=views.items(folder="ab", field="qid"),
    )
