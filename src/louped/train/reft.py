"""`louped train reft`: a low-rank representation intervention (LoReFT, pyreft) on a model's
residual stream, as an MLflow training run like the other recipes.

pyreft pins an older transformers than louped, so training runs in an environment of its own that
uv builds and caches on first use (`uvx`); louped only needs uv on the PATH. The worker
(reft_worker.py, which imports nothing from louped) reads the job as JSON, trains, and writes its
loss to metrics.jsonl as it goes, which this side logs to the run live, then its replies on the
test set with and without the intervention, which become the run's table and scores. The trained
intervention stays in <output_dir>/reft for pyreft to load.

The intervention sits at the last prompt token of every listed layer's block output, the position
pyreft's own examples use, so it runs on the prompt once and steers everything generated after it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, Field

from louped.data import Example, read_jsonl
from louped.train.base import TrainError, _flat, _Strict, _under_home, model_path

#: The pyreft the worker runs; its own transformers and torch come with it.
PYREFT = "pyreft==0.1.0"
PYTHON = "3.11"


class ReftSchedule(_Strict):
    epochs: float = 10
    max_steps: int = -1
    per_device_batch_size: int = 8
    learning_rate: float = 4e-3
    logging_steps: int = 5
    seed: int = 0


class ReftConfig(_Strict):
    """A reft YAML file."""

    name: str
    experiment: str | None = None
    base_model: str
    dataset: Path
    """Examples (louped data's JSONL): the messages are the prompt, the reply the target."""
    output_dir: Path
    layers: list[int] = Field(default_factory=lambda: [8])
    """Block outputs to intervene on, one LoReFT each."""
    rank: int = 4
    test: Path | None = None
    """Examples to reply to after training, with and without the intervention."""
    max_new_tokens: int = 64
    train: ReftSchedule = ReftSchedule()


class ReftPlan(BaseModel):
    name: str
    base_model: str
    examples: int
    test: int
    layers: list[int]
    rank: int


def load_config(path: Path) -> ReftConfig:
    import yaml

    if not path.exists():
        raise TrainError(f"no config at {path}")
    try:
        cfg = ReftConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise TrainError(f"{path}: {exc}") from exc
    test = _under_home(cfg.test) if cfg.test else None
    return cfg.model_copy(update={"dataset": _under_home(cfg.dataset), "test": test,
                                  "output_dir": _under_home(cfg.output_dir)})  # fmt: skip


def _examples(path: Path) -> list[Example]:
    try:
        rows = read_jsonl(path)
    except FileNotFoundError as exc:
        raise TrainError(f"no examples at {path}") from exc
    if not rows:
        raise TrainError(f"{path} is empty")
    return rows


def plan(cfg: ReftConfig) -> ReftPlan:
    return ReftPlan(name=cfg.name, base_model=cfg.base_model,
                    examples=len(_examples(cfg.dataset)),
                    test=len(_examples(cfg.test)) if cfg.test else 0,
                    layers=cfg.layers, rank=cfg.rank)  # fmt: skip


def job(cfg: ReftConfig) -> dict:
    """What the worker reads: plain JSON, nothing of louped's."""

    def pairs(rows: list[Example]) -> list[dict]:
        return [{"messages": e.messages, "reply": e.reply} for e in rows]

    return {"model": model_path(cfg.base_model), "layers": cfg.layers, "rank": cfg.rank,
            "train": pairs(_examples(cfg.dataset)),
            "test": pairs(_examples(cfg.test)) if cfg.test else [],
            "max_new_tokens": cfg.max_new_tokens, "out": str(cfg.output_dir),
            **cfg.train.model_dump()}  # fmt: skip


def command(job_file: Path) -> list[str]:
    uvx = shutil.which("uvx")
    if uvx is None:
        raise TrainError("louped train reft runs pyreft through uv: install uv (pip install uv)")
    worker = Path(__file__).with_name("reft_worker.py")
    # a uv-managed Python ships its headers, which Triton compiles its CUDA helpers against
    return [uvx, "--managed-python", "--python", PYTHON, "--from", PYREFT, "python", str(worker),
            str(job_file)]  # fmt: skip


def train(cfg: ReftConfig) -> Path:
    """Train in pyreft's environment, logging the loss as it comes; returns the intervention."""
    import mlflow

    from louped.analysis import table
    from louped.tracking import log_json, start_run

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    job_file = cfg.output_dir / "job.json"
    job_file.write_text(json.dumps(job(cfg)))
    metrics = cfg.output_dir / "metrics.jsonl"
    metrics.unlink(missing_ok=True)
    params = {"recipe": "reft", "model": cfg.base_model, **_flat(cfg.model_dump(mode="json"))}
    with start_run(cfg.experiment or cfg.name, name=f"reft · {cfg.name}", params=params,
                   seed=cfg.train.seed, kind="training") as run:  # fmt: skip
        # uv may fetch its managed Python even when the user's uv config says downloads are manual
        env = os.environ | {"UV_PYTHON_DOWNLOADS": "automatic"}
        proc = subprocess.Popen(command(job_file), env=env)
        seen = 0
        while True:  # the worker's loss, logged as it writes it
            done = proc.poll() is not None
            lines = metrics.read_text().splitlines() if metrics.exists() else []
            for line in lines[seen:]:
                point = json.loads(line)
                step = int(point.pop("step"))
                mlflow.log_metrics({k: float(v) for k, v in point.items()}, step=step)
            seen = len(lines)
            if done:
                break
            time.sleep(2)
        if proc.returncode != 0:
            raise TrainError(f"the pyreft worker failed with exit code {proc.returncode}")
        replies = cfg.output_dir / "replies.json"
        if replies.exists():
            rows = json.loads(replies.read_text())
            for side in ("base", "reft"):
                hits = [float(r["target"].lower() in r[side].lower()) for r in rows]
                words = [len(r[side].split()) for r in rows]
                mlflow.log_metrics({f"test/{side}_contains_target": sum(hits) / len(hits),
                                    f"test/{side}_words": sum(words) / len(words)})  # fmt: skip
            log_json(table("Test replies, base and with the intervention",
                           ["prompt", "target", "base", "reft"],
                           [[r["prompt"], r["target"], r["base"], r["reft"]] for r in rows],
                           about="Held-out prompts answered by the base model and with the "
                           "trained intervention, beside the reply it was trained toward."),
                     "views/00-replies.json")  # fmt: skip
        adapter = cfg.output_dir / "reft"
        mlflow.set_tag("louped.adapter", str(adapter))
        print(f"run m-{run.info.run_id}: intervention at {adapter}")
    return adapter
