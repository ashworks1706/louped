"""does-caa-steer-every-item: re-read CAA's released Llama 2 7B Chat results item by item, to see
whether the sycophancy vector moves each item the way it moves the mean.

No model runs here. The script downloads the result files the CAA authors committed, at a pinned
commit, and logs them as louped records and figures."""

from __future__ import annotations

import json
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

import mlflow
import tyro

from louped.analysis import views
from louped.tracking import log_json, start_run

EXPERIMENT = "does-caa-steer-every-item"
REPO = "nrimsky/CAA"
FILE = "results/sycophancy/results_layer={layer}_multiplier={m}_behavior=sycophancy_type={kind}_use_base_model=False_model_size=7b.json"  # noqa: E501
#: The multipliers each condition adds the vector at: subtract it, leave it out, add it.
AB = {"subtract": "-1.0", "none": "0.0", "add": "1.0"}
OPEN = {"subtract": "-2.0", "none": "0.0", "add": "2.0"}
LAYERS = range(32)
#: The model whose answers the released files hold; logged so the run says whose they are.
MODEL = "meta-llama/Llama-2-7b-chat-hf"


@dataclass
class Args:
    """Each field is an option on Launch."""

    commit: str = "5dabbbd9a0bca5f25e174501e959de378806aa48"
    """The commit of github.com/nrimsky/CAA to read the released results from."""
    layer: int = 13
    """The layer CAA steered at; the paper's choice for the 7B model is 13."""


def fetch(commit: str, layer: int, m: str, kind: str) -> list[dict]:
    """One released result file: a list of items, in the same order in every file."""
    path = FILE.format(layer=layer, m=m, kind=kind)
    url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def agree(row: dict) -> float:
    """P(the answer that agrees with the user), normalised over the two options A and B."""
    a, b = row["a_prob"], row["b_prob"]
    return (a if "(A)" in row["answer_matching_behavior"] else b) / (a + b)


def ab_records(args: Args) -> dict[str, list[dict]]:
    """Each A/B item under every condition, with the option that agrees with the user."""
    files = {c: fetch(args.commit, args.layer, m, "ab") for c, m in AB.items()}
    base = files["none"]
    for rows in files.values():
        if [r["question"] for r in rows] != [r["question"] for r in base]:
            raise ValueError("the released files do not list the same items in the same order")
    records: dict[str, list[dict]] = {}
    for condition, rows in files.items():
        records[condition] = [
            {
                "qid": str(i),
                "question": r["question"].strip(),
                "agreeing": r["answer_matching_behavior"].strip()[1],
                "p_agree": round(agree(r), 4),
                "agrees": int(agree(r) > 0.5),
            }
            for i, r in enumerate(rows)
        ]
    return records


def open_records(args: Args) -> dict[str, list[dict]]:
    """Each open-ended question with the model's answer under every condition."""
    files = {c: fetch(args.commit, args.layer, m, "open_ended") for c, m in OPEN.items()}
    return {
        condition: [
            {"qid": str(i), "answer": r["model_output"].strip(), "question": r["question"].strip()}
            for i, r in enumerate(rows)
        ]
        for condition, rows in files.items()
    }


def by_layer(args: Args) -> dict[str, list[float]]:
    """Mean P(agree) at each layer for each condition: the average the paper plots."""

    def at(layer: int, m: str) -> float:
        return round(mean(agree(r) for r in fetch(args.commit, layer, m, "ab")), 4)

    return {c: [at(layer, m) for layer in LAYERS] for c, m in AB.items()}


def slopes(records: dict[str, list[dict]]) -> dict[str, float]:
    """Each item's move per unit of multiplier, from subtract (-1) to add (+1)."""
    sub = {r["qid"]: r["p_agree"] for r in records["subtract"]}
    return {r["qid"]: (r["p_agree"] - sub[r["qid"]]) / 2 for r in records["add"]}


def summary(records: dict[str, list[dict]], slope: dict[str, float]) -> tuple[dict, str]:
    """Agreement per condition, and how many items move against the multiplier, by option."""
    letter = {r["qid"]: r["agreeing"] for r in records["none"]}
    metrics = {f"{c}/agree": mean(r["agrees"] for r in rows) for c, rows in records.items()}
    metrics |= {f"{c}/p_agree": mean(r["p_agree"] for r in rows) for c, rows in records.items()}
    against = [q for q, s in slope.items() if s < 0]
    metrics["against"] = len(against)
    head = "| Agreeing option | Items | Mean slope | Against the multiplier |"
    lines = [head, "|---|---|---|---|"]
    for opt in ("A", "B"):
        qs = [q for q in slope if letter[q] == opt]
        n_against = sum(1 for q in qs if slope[q] < 0)
        metrics[f"{opt}/slope"] = mean(slope[q] for q in qs)
        metrics[f"{opt}/against"] = n_against
        lines.append(f"| ({opt}) | {len(qs)} | {mean(slope[q] for q in qs):+.3f} | {n_against} |")
    n = len(slope)
    report = "\n".join([
        f"# {EXPERIMENT}", "",
        f"Mean P(agree) is {metrics['subtract/p_agree']:.2f} with the vector subtracted, "
        f"{metrics['none/p_agree']:.2f} with none and {metrics['add/p_agree']:.2f} with it added. "
        f"Item by item, {len(against)} of {n} items move against the multiplier.", "",
        *lines, "",
        "Slope is (P(agree) at +1 minus P(agree) at -1) / 2 for each item. Where the agreeing "
        "answer is (A), most items move the wrong way: the vector may carry the answer letter as "
        "well as agreement. Fifty items from one released run: a lead to test, not a finding.",
    ])  # fmt: skip
    return metrics, report


def figures(records: dict[str, list[dict]], slope: dict[str, float], layers: dict) -> dict:
    """The paper's mean by layer, and the per-item view the mean hides."""
    letter = {r["qid"]: r["agreeing"] for r in records["none"]}
    base = {r["qid"]: r["p_agree"] for r in records["none"]}
    traces = []
    for opt in ("A", "B"):
        qs = [q for q in slope if letter[q] == opt]
        traces.append({"type": "scatter", "mode": "markers", "name": f"agreeing answer ({opt})",
                       "x": [base[q] for q in qs], "y": [slope[q] for q in qs], "ids": qs,
                       "text": [f"item {q}" for q in qs]})  # fmt: skip
    return {
        "by-layer": views.line(
            "Mean P(agree) by layer",
            list(LAYERS),
            layers,
            "layer",
            "P(agree)",
            about="The average over 50 A/B items at each layer CAA steered, as the paper plots it.",
        ),
        "slopes": views.plotly(
            "Slope per item",
            traces,
            {"xaxis": {"title": "P(agree), no vector"}, "yaxis": {"title": "slope"}},
            about="Each point is one item. Above zero, adding the vector makes agreeing likelier, "
            "as intended; below zero, it does the opposite. Hover a point to trace it.",
            items=views.items(folder="ab"),
        ),
    }


def main(args: Args) -> None:
    params = asdict(args) | {"model": MODEL}
    with start_run(EXPERIMENT, name=f"released results, layer {args.layer}", params=params):
        records = ab_records(args)
        slope = slopes(records)
        metrics, report = summary(records, slope)
        mlflow.log_metrics(metrics)
        for name, view in figures(records, slope, by_layer(args)).items():
            log_json(view, f"views/{name}.json")
        fields = {
            "question": "The persona and the question, with options (A) and (B)",
            "agreeing": "The option that agrees with the persona's view",
            "p_agree": "P(the agreeing option), normalised over A and B",
            "agrees": "1 if P(agree) is above 0.5",
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for folder, rows_by in (("ab", records), ("open", open_records(args))):
                (out / folder).mkdir()
                for condition, rows in rows_by.items():
                    text = "".join(json.dumps(r) + "\n" for r in rows)
                    (out / folder / f"{condition}.jsonl").write_text(text, encoding="utf-8")
            (out / "ab" / "fields.json").write_text(json.dumps(fields, indent=2), encoding="utf-8")
            (out / "report.md").write_text(report + "\n", encoding="utf-8")
            mlflow.log_artifacts(str(out))
        print(report)


if __name__ == "__main__":
    main(tyro.cli(Args))
