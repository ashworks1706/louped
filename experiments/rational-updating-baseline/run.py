"""The unmitigated baseline of Ma et al., "Sycophancy Suppression Can Impair Rational Updating"
(arXiv 2608.26511), run with the authors' harness before any mitigation is added.

    uv run --all-extras python experiments/rational-updating-baseline/run.py          # 20 items
    uv run --all-extras python experiments/rational-updating-baseline/run.py --limit None
    uv run --all-extras python experiments/rational-updating-baseline/run.py --tiny   # offline

1. Setup: the harness (`sru`) at a pinned commit, in its own uv environment under
   .loupe/vendor, constrained to loupe's lock (the harness pins nothing). Its tests run when
   the environment is built, `sru verify-data` every run; output goes to setup.log.
2. Preflight: a 16 GB CUDA device, access to the gated model at the paper's revision, its chat
   template hash against the published one, free space in the Hub cache. Stops with what is
   missing; --tiny skips it.
3. Run: `sru run` with revision, dtype, device map and scoring explicit. The command, the
   harness config, freeze and RunMeta are saved next to its report, which compares rates and
   denominators with the paper's when the model is one of its four backbones; rates,
   denominators and files also go to an MLflow run. A rerun into the same directory resumes
   only under the same command and environment.
4. Examples: examples.md, ten items to read by hand (yielded, held, updated, not updated),
   rebuilt with the harness's own conversation builder.

--tiny swaps in loupe's tiny random Qwen2 so prompts, scoring and the report can be checked
without a GPU or the Hub. Its numbers are noise.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import mlflow
import tyro

from loupe.core import capture, home
from loupe.tracking import start_run

EXPERIMENT = "rational-updating-baseline"
SRU_REPO = "https://github.com/dependentsign/sycophancy-rational-updating"
SRU_COMMIT = "36974db6bb1dc6bb31ff9fb56c9201beed78edd8"
HERE = Path(__file__).parent


@dataclass
class Args:
    model: str = "meta-llama/Llama-3.1-8B-Instruct"
    """The paper's main backbone; the harness loads the revision its published rates used."""
    datasets: str = "truthfulqa"
    conditions: str = "baseline,pressure,evidence,user_evidence"
    """The four the paper reports."""
    split: str = "test"
    """The harness's held-out split; its reference table has test and cal rows."""
    limit: int | None = 20
    """First N items of the split; None is all of it, the only run comparable with the paper."""
    batch_size: int = 8
    examples: int = 10
    seed: int = 0
    """Which examples are drawn for reading; decoding is greedy."""
    tiny: bool = False
    """Offline plumbing check on a tiny random model; skips preflight."""
    out: str | None = None
    """Run directory; default .loupe/runs/rational-updating-baseline/<model>_<split>[_n<limit>]."""


def sh(cmd: list[str], log: Path | None = None, cwd: Path | None = None, env=None) -> str:
    """Run a command, echo it, append its output to log, raise on failure; returns stdout."""
    print("$ " + " ".join(cmd), flush=True)
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if log:
        with log.open("a", encoding="utf-8") as f:
            f.write(f"$ {' '.join(cmd)}\n{done.stdout}{done.stderr}\n[exit {done.returncode}]\n\n")
    if done.returncode:
        tail = (done.stdout + done.stderr)[-2000:]
        raise SystemExit(f"failed ({done.returncode}): {' '.join(cmd)}\n{tail}")
    return done.stdout


def setup() -> tuple[Path, Path]:
    """The harness checkout and its environment, rebuilt when loupe's lock moves; its tests and
    data check run every time."""
    root = home() / "vendor"
    repo, venv = root / "sycophancy-rational-updating", root / "sru-venv"
    log, marker = root / "setup.log", venv / "loupe-built"
    root.mkdir(parents=True, exist_ok=True)
    if not repo.exists():
        sh(["git", "clone", SRU_REPO, str(repo)], log)
        sh(["git", "checkout", "--detach", SRU_COMMIT], log, cwd=repo)
    head = sh(["git", "rev-parse", "HEAD"], cwd=repo).strip()
    if head != SRU_COMMIT or sh(["git", "status", "--porcelain"], cwd=repo).strip():
        raise SystemExit(f"{repo} is at {head} or has local changes; expected {SRU_COMMIT}")
    # The harness sets only lower bounds (torch>=2.1, transformers>=4.51, accelerate>=0.26) and
    # the paper states no versions, so every shared package follows loupe's lock.
    lock = sh(["uv", "export", "--all-extras", "--no-hashes", "--no-emit-project", "--frozen"])
    stamp = hashlib.sha256((SRU_COMMIT + lock).encode()).hexdigest()
    python = venv / "bin" / "python"
    if not marker.exists() or marker.read_text() != stamp:
        constraints = root / "constraints.txt"
        constraints.write_text(lock)
        sh(["uv", "venv", "--clear", str(venv), "--python", sys.executable], log)
        sh(["uv", "pip", "install", "--python", str(python), "-c", str(constraints),
            "-e", f"{repo}[hf,dev]"], log)  # fmt: skip
        sh([str(python), "-m", "pytest", "-q", str(repo / "tests")], log, cwd=repo)
        marker.write_text(stamp)
    sh([str(venv / "bin" / "sru"), "verify-data"], log, cwd=repo)
    return repo, python


PROBE = """
import json, shutil, sys, torch
from pathlib import Path
from huggingface_hub import constants, hf_hub_download
from transformers import AutoTokenizer
from sru.models import expected_template_hash, pinned_revision, template_hash
model = sys.argv[1]
out = {"revision": pinned_revision(model), "expected_template": expected_template_hash(model),
       "gpu_bytes": [torch.cuda.get_device_properties(i).total_memory
                     for i in range(torch.cuda.device_count())],
       "hf_cache": constants.HF_HUB_CACHE}
cache = Path(constants.HF_HUB_CACHE)
while not cache.exists():  # measure the filesystem the weights will land on
    cache = cache.parent
out["cache_free_bytes"] = shutil.disk_usage(cache).free
try:
    hf_hub_download(model, "config.json", revision=out["revision"])
    out["template"] = template_hash(AutoTokenizer.from_pretrained(model, revision=out["revision"]))
    out["model_access"] = "ok"
except Exception as e:
    out["model_access"] = f"{type(e).__name__}: {str(e)[:300]}"
print(json.dumps(out))
"""


def preflight(python: Path, model: str) -> dict:
    """What the run needs that this machine may not have; raises listing what is missing."""
    found = json.loads(sh([str(python), "-c", PROBE, model]).strip().splitlines()[-1])
    print(json.dumps(found, indent=2))
    missing = []
    if max(found["gpu_bytes"], default=0) < 16e9:
        missing.append(f"no CUDA device with 16 GB (found {found['gpu_bytes']} bytes); "
                       "the 8B model in bf16 needs about 16 GB")  # fmt: skip
    if found["model_access"] != "ok":
        missing.append(f"cannot read {model}: {found['model_access']}")
    elif found["expected_template"] and found["template"] != found["expected_template"]:
        missing.append(f"chat template {found['template']} is not the published "
                       f"{found['expected_template']}")  # fmt: skip
    if found["cache_free_bytes"] < 20e9:
        missing.append(f"{found['cache_free_bytes'] / 1e9:.1f} GB free at {found['hf_cache']}; "
                       "the 8B weights take about 16 GB")  # fmt: skip
    if missing:
        raise SystemExit("preflight failed:\n- " + "\n- ".join(missing))
    return found


def tiny_model() -> str:
    from loupe.models import save_model
    from loupe.models.tiny import tiny

    lm = tiny()
    return str(save_model(lm, lm.tokenizer, f"{EXPERIMENT}-tiny"))


def headline(out: Path) -> dict[str, float]:
    """The rates and their denominators per dataset, from the harness's metrics.json."""
    metrics: dict[str, float] = {}
    for ds, d in json.loads((out / "metrics.json").read_text())["datasets"].items():
        if "headline" not in d:
            continue
        metrics |= {f"{ds}/{k}": v for k, v in d["headline"].items() if v is not None}
        conds = d["conditions"]
        metrics[f"{ds}/n_items"] = d["n_items"]
        metrics[f"{ds}/n_uy_denom"] = conds["pressure"]["flip_correct_to_wrong"]["n"]
        metrics[f"{ds}/n_ru_denom"] = conds["evidence"]["flip_wrong_to_correct"]["n"]
    return metrics


def main(args: Args) -> None:
    repo, python = setup()
    found = None if args.tiny else preflight(python, args.model)
    model = tiny_model() if args.tiny else args.model
    name = Path(model).name if args.tiny else model.replace("/", "_")
    name += f"_{args.split}" + (f"_n{args.limit}" if args.limit else "")
    out = Path(args.out) if args.out else home() / "runs" / EXPERIMENT / name
    cmd = [str(python.parent / "sru"), "run", "--model", model, "--backend", "hf",
           "--datasets", args.datasets, "--conditions", args.conditions, "--split", args.split,
           "--tqa-scoring", "loglik", "--batch-size", str(args.batch_size), "--out", str(out),
           "--yes"]  # fmt: skip
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    env = None
    if args.tiny:  # float32 on CPU without accelerate; the paper's runs are bf16 on GPU
        cmd += ["--dtype", "float32", "--device-map", "none"]
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    else:
        cmd += ["--dtype", "bfloat16", "--device-map", "auto", "--revision", found["revision"]]
    freeze = sh(["uv", "pip", "freeze", "--python", str(python)])
    # The harness resumes from raw/ and checks only its protocol keys; a resume under another
    # command or environment would mix records from two setups under one provenance.
    for file, text in (("command.txt", " ".join(cmd) + "\n"), ("freeze.txt", freeze)):
        if (out / file).exists() and (out / file).read_text() != text:
            raise SystemExit(f"{out} holds a run with another {file}; pass a new --out")
    out.mkdir(parents=True, exist_ok=True)
    (out / "command.txt").write_text(" ".join(cmd) + "\n")
    (out / "freeze.txt").write_text(freeze)
    record = {**asdict(args), "model": model, "sru_commit": SRU_COMMIT, "preflight": found}
    (out / "loupe-args.json").write_text(json.dumps(record, indent=2) + "\n")
    capture(seed=args.seed).write(out / "meta.json")
    with start_run(EXPERIMENT, name=f"baseline · {name}", params=record, seed=args.seed):
        log = sh(cmd, out / "sru.log", cwd=repo, env=env)
        if found and found["expected_template"] and "template   matches" not in log:
            raise SystemExit(f"the harness did not confirm the published chat template; see {out}")
        sh([str(python), str(HERE / "examples.py"), str(out), "--n", str(args.examples),
            "--seed", str(args.seed)], cwd=repo)  # fmt: skip
        mlflow.log_metrics(headline(out))
        for file in ("report.md", "examples.md", "metrics.json", "config.json", "command.txt",
                     "freeze.txt", "loupe-args.json", "meta.json"):  # fmt: skip
            mlflow.log_artifact(str(out / file))
    print((out / "report.md").read_text())
    if args.limit:
        print(f"first {args.limit} items only: not comparable with the published rates")
    print(f"run directory: {out}")


if __name__ == "__main__":
    main(tyro.cli(Args))
