"""Feature dashboards for an SAE over a dataset, as one analysis run the app's Feature page reads.

    loupe features --model gpt2 --sae gpt2-small-res-jb --sae-id blocks.8.hook_resid_pre

The model loads through loupe (a Hub id, a path or a saved name), the SAE through SAELens (a
release and id from its registry, or a local directory), the texts from a .txt file (one per line),
a .jsonl file or any Hugging Face dataset. Each dashboard is features/<feature>.json in the run;
views/ holds a table of them that links to each one's page. Needs the sae extra, and datasets for a
Hub dataset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loupe.analysis import feature_dashboards, table
from loupe.tracking import log_json, start_run


def texts(dataset: str, split: str = "train", column: str = "text", n: int = 256) -> list[str]:
    """The first n non-empty texts of a .txt or .jsonl file, or of a Hugging Face dataset."""
    path = Path(dataset)
    if path.suffix in (".txt", ".jsonl") and not path.exists():
        raise FileNotFoundError(path)
    if path.suffix == ".txt":
        rows: list[str] = path.read_text(encoding="utf-8").splitlines()
    elif path.suffix == ".jsonl":
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [str(json.loads(line)[column]) for line in lines if line.strip()]
    else:
        from datasets import load_dataset

        stream = load_dataset(dataset, split=split, streaming=True)
        rows = []
        for record in stream:
            rows.append(str(record[column]))  # pyright: ignore[reportArgumentType, reportCallIssue]
            if len(rows) >= n * 2:  # room for the empty ones
                break
    return [r for r in rows if r.strip()][:n]


def load_sae(sae: str, sae_id: str | None, device: str) -> Any:
    from sae_lens import SAE

    if sae_id:
        return SAE.from_pretrained(sae, sae_id, device=device)
    return SAE.load_from_disk(sae, device=device)


def features(
    model: str,
    sae: str,
    sae_id: str | None = None,
    dataset: str = "NeelNanda/pile-10k",
    split: str = "train",
    column: str = "text",
    n: int = 256,
    max_tokens: int = 128,
    only: list[int] | None = None,
    top_n: int = 24,
    k: int = 8,
    experiment: str = "features",
    revision: str | None = None,
) -> str:
    """Dashboards for the SAE's features on the dataset: `only` those, else the top_n that peak
    highest. Returns the run id."""
    from loupe.models import load

    lm = load(model, revision=revision)
    device = str(next(lm._model.parameters()).device)
    encoder = load_sae(sae, sae_id, device)
    prompts = []
    for text in texts(dataset, split, column, n):
        ids = lm.tokenizer(text)["input_ids"][:max_tokens]
        prompts.append(str(lm.tokenizer.decode(ids, skip_special_tokens=True)))
    dashes = feature_dashboards(lm, encoder, prompts, only, top_n, k)
    hook = str(encoder.cfg.metadata.hook_name)
    params = {"model": model, "sae": sae, "sae_id": sae_id or "", "hook": hook,
              "dataset": dataset, "split": split, "texts": len(prompts),
              "max_tokens": max_tokens, "features": len(dashes)}  # fmt: skip
    with start_run(experiment, name=f"features · {sae_id or sae}", params=params) as run:
        run_id = f"m-{run.info.run_id}"
        for d in dashes:
            log_json(
                {**d, "model": model, "sae": sae, "sae_id": sae_id}, f"features/{d['feature']}.json"
            )
        rows = [[f"#{d['feature']}", d["density"], d["max"],
                 " ".join(t for t, _ in d["promoted"][:5])] for d in dashes]  # fmt: skip
        links = [[f"/feature/?run={run_id}&f={d['feature']}", None, None, None] for d in dashes]
        log_json(table(f"SAE features at {hook}", ["feature", "density", "max", "promotes"], rows,
                       note=f"{len(prompts)} texts; a feature opens its dashboard", links=links,
                       about="density: share of tokens where the feature fires. max: its "
                       "peak activation. promotes: tokens it pushes up in the output."),
                 "views/00-features.json")  # fmt: skip
    return run_id
