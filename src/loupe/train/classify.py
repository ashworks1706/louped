"""A small text classifier: a frozen sentence encoder and logistic regression on its embeddings.

For decisions an application makes with keyword rules or a model call (whether a message asks to be
remembered, which tool family a request needs): cheap to train on a CPU, fast to run, and scored on
a held-out split so it can be compared to the rule it would replace. Rows are JSONL with text and
label; the split is by a hash of the text. The classifier is saved with joblib. Needs the rag extra.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from loupe.data.collect import bucket
from loupe.train.base import TrainError, _Strict, _under_home


class Row(BaseModel):
    text: str
    label: str


class ClassifyConfig(_Strict):
    """A classify YAML file."""

    name: str
    experiment: str | None = None
    encoder: str
    """A sentence-transformers model by Hub id or path."""
    dataset: Path
    output_dir: Path
    test_fraction: float = 0.2
    c: float = 1.0
    """Inverse regularisation strength of the logistic regression."""
    seed: int = 0


class ClassifyPlan(BaseModel):
    name: str
    encoder: str
    rows: int
    labels: dict[str, int]


def load_config(path: Path) -> ClassifyConfig:
    import yaml

    if not path.exists():
        raise TrainError(f"no config at {path}")
    cfg = ClassifyConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return cfg.model_copy(update={"dataset": _under_home(cfg.dataset),
                                  "output_dir": _under_home(cfg.output_dir)})  # fmt: skip


def _rows(cfg: ClassifyConfig) -> list[Row]:
    if not cfg.dataset.exists():
        raise TrainError(f"no dataset at {cfg.dataset}")
    lines = cfg.dataset.read_text(encoding="utf-8").splitlines()
    return [Row.model_validate_json(line) for line in lines if line.strip()]


def plan(cfg: ClassifyConfig) -> ClassifyPlan:
    rows = _rows(cfg)
    labels = {
        label: sum(r.label == label for r in rows) for label in sorted({r.label for r in rows})
    }
    return ClassifyPlan(name=cfg.name, encoder=cfg.encoder, rows=len(rows), labels=labels)


def train(cfg: ClassifyConfig) -> Path:
    """Fit, score on the held-out split, log to MLflow; returns the saved classifier."""
    import joblib
    import mlflow
    from sentence_transformers import SentenceTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report, f1_score

    from loupe.tracking import start_run

    rows = _rows(cfg)
    test = [r for r in rows if bucket(r.text) < cfg.test_fraction]
    fit = [r for r in rows if bucket(r.text) >= cfg.test_fraction]
    if not test or len({r.label for r in fit}) < 2:
        raise TrainError("need two labels to train on and at least one held-out row")
    params = {**cfg.model_dump(mode="json"), "rows": len(rows), "test_rows": len(test)}
    with start_run(cfg.experiment or cfg.name, name=f"classify · {cfg.name}", params=params,
                   seed=cfg.seed, kind="training") as run:  # fmt: skip
        encoder = SentenceTransformer(cfg.encoder)
        clf = LogisticRegression(C=cfg.c, max_iter=1000, random_state=cfg.seed)
        clf.fit(encoder.encode([r.text for r in fit]), [r.label for r in fit])
        pred = clf.predict(encoder.encode([r.text for r in test]))
        gold = [r.label for r in test]
        mlflow.log_metrics({"accuracy": float(accuracy_score(gold, pred)),
                            "macro_f1": float(f1_score(gold, pred, average="macro"))})  # fmt: skip
        report = classification_report(gold, pred, output_dict=True)
        mlflow.log_text(json.dumps(report, indent=2), "report.json")
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        path = cfg.output_dir / "classifier.joblib"
        joblib.dump({"encoder": cfg.encoder, "classifier": clf}, path)
        mlflow.set_tag("loupe.classifier", str(path))
        print(f"run m-{run.info.run_id}: classifier at {path}")
    return path
