"""The unmitigated baseline of Ma et al., "Sycophancy Suppression Can Impair Rational Updating"
(arXiv 2608.26511), run with the authors' harness before any mitigation is added.

    uv run --all-extras python experiments/rational-updating-baseline/run.py          # 20 items
    uv run --all-extras python experiments/rational-updating-baseline/run.py --limit None
    uv run --all-extras python experiments/rational-updating-baseline/run.py --tiny   # offline

1. Setup: the harness (`sru`) at a pinned commit, in its own uv environment under
   .loupe/vendor, with torch, transformers and accelerate pinned to loupe's versions (the
   harness pins none). Its tests and `sru verify-data` run there; output goes to setup.log.
2. Preflight: CUDA, access to the gated model at the paper's revision, free disk. Stops with
   what is missing; --tiny skips it.
3. Run: `sru run` with every protocol flag explicit. The command, the harness config, freeze
   and RunMeta are saved next to its report, which compares rates and denominators with the
   paper's when the model is one of its four backbones.
4. Examples: examples.md, ten items to read by hand (yielded, held, updated, not updated),
   rebuilt with the harness's own conversation builder.

--tiny swaps in loupe's tiny random Qwen2 so prompts, scoring and the report can be checked
without a GPU or the Hub. Its numbers are noise.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import tyro

from loupe.core import capture, home

EXPERIMENT = "rational-updating-baseline"
SRU_REPO = "https://github.com/dependentsign/sycophancy-rational-updating"
SRU_COMMIT = "36974db6bb1dc6bb31ff9fb56c9201beed78edd8"
#: The harness only sets lower bounds (torch>=2.1, transformers>=4.51, accelerate>=0.26) and the
#: paper does not state its versions, so these follow loupe's lock and are recorded per run.
PINNED = ("torch", "transformers", "accelerate")
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
    tiny: bool = False
    """Offline plumbing check on a tiny random model; skips preflight."""
    out: str | None = None
    """Run directory; default .loupe/runs/rational-updating-baseline/<model>_<split>[_n<limit>]."""


def sh(cmd: list[str], log: Path | None = None, cwd: Path | None = None) -> str:
    """Run a command, echo it, append both to log, raise on failure."""
    print("$ " + " ".join(cmd), flush=True)
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = done.stdout + done.stderr
    if log:
        with log.open("a", encoding="utf-8") as f:
            f.write(f"$ {' '.join(cmd)}\n{out}\n[exit {done.returncode}]\n\n")
    if done.returncode:
        raise SystemExit(f"failed ({done.returncode}): {' '.join(cmd)}\n{out[-2000:]}")
    return out


def setup() -> tuple[Path, Path]:
    """The harness checkout and its environment's python, built once and verified every run."""
    root = home() / "vendor"
    repo, venv = root / "sycophancy-rational-updating", root / "sru-venv"
    log = root / "setup.log"
    root.mkdir(parents=True, exist_ok=True)
    if not repo.exists():
        sh(["git", "clone", SRU_REPO, str(repo)], log)
        sh(["git", "checkout", "--detach", SRU_COMMIT], log, cwd=repo)
    head = sh(["git", "rev-parse", "HEAD"], cwd=repo).strip()
    if head != SRU_COMMIT or sh(["git", "status", "--porcelain"], cwd=repo).strip():
        raise SystemExit(f"{repo} is at {head} or has local changes; expected {SRU_COMMIT}")
    python = venv / "bin" / "python"
    if not python.exists():
        sh(["uv", "venv", str(venv), "--python", sys.executable], log)
        pins = [f"{p}=={version(p)}" for p in PINNED]
        sh(["uv", "pip", "install", "--python", str(python), "-e", f"{repo}[hf,dev]", *pins], log)
        sh([str(python), "-m", "pytest", "-q", str(repo / "tests")], log, cwd=repo)
        sh([str(venv / "bin" / "sru"), "verify-data"], log, cwd=repo)
    return repo, python


def preflight(python: Path, model: str) -> dict:
    """What the run needs that this machine may not have; raises listing what is missing."""
    probe = (
        "import json, torch\n"
        "from huggingface_hub import hf_hub_download\n"
        "from sru.models import pinned_revision\n"
        f"model = {model!r}\n"
        "out = {'cuda': torch.cuda.is_available(), 'gpus': [\n"
        "    [torch.cuda.get_device_name(i), torch.cuda.get_device_properties(i).total_memory]\n"
        "    for i in range(torch.cuda.device_count())], 'revision': pinned_revision(model)}\n"
        "try:\n"
        "    hf_hub_download(model, 'config.json', revision=out['revision'])\n"
        "    out['model_access'] = 'ok'\n"
        "except Exception as e:\n"
        "    out['model_access'] = f'{type(e).__name__}: {str(e)[:300]}'\n"
        "print(json.dumps(out))\n"
    )
    found = json.loads(sh([str(python), "-c", probe]).strip().splitlines()[-1])
    found["disk_free_gb"] = round(shutil.disk_usage(home()).free / 1e9, 1)
    print(json.dumps(found, indent=2))
    missing = []
    if not found["cuda"]:
        missing.append("no CUDA device (an 8B model in bf16 needs about 16 GB of GPU memory)")
    if found["model_access"] != "ok":
        missing.append(f"cannot read {model}: {found['model_access']}")
    if found["disk_free_gb"] < 20:
        missing.append(f"{found['disk_free_gb']} GB free; the 8B weights take about 16 GB")
    if missing:
        raise SystemExit("preflight failed:\n- " + "\n- ".join(missing))
    return found


def tiny_model() -> str:
    from loupe.models import save_model
    from loupe.models.tiny import tiny

    lm = tiny()
    return str(save_model(lm, lm.tokenizer, f"{EXPERIMENT}-tiny"))


def main(args: Args) -> None:
    repo, python = setup()
    found = None if args.tiny else preflight(python, args.model)
    model = tiny_model() if args.tiny else args.model
    name = Path(model).name if args.tiny else model.replace("/", "_")
    name += f"_{args.split}" + (f"_n{args.limit}" if args.limit else "")
    out = Path(args.out) if args.out else home() / "runs" / EXPERIMENT / name
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(python.parent / "sru"), "run", "--model", model, "--backend", "hf",
           "--datasets", args.datasets, "--conditions", args.conditions, "--split", args.split,
           "--tqa-scoring", "loglik", "--batch-size", str(args.batch_size), "--out", str(out),
           "--yes"]  # fmt: skip
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.tiny:  # float32 on CPU without accelerate; the paper's runs are bf16 on GPU
        cmd += ["--dtype", "float32", "--device-map", "none"]
    capture().write(out / "meta.json")
    record = {**asdict(args), "sru_commit": SRU_COMMIT, "preflight": found}
    (out / "loupe-args.json").write_text(json.dumps(record, indent=2) + "\n")
    (out / "command.txt").write_text(" ".join(cmd) + "\n")
    (out / "freeze.txt").write_text(sh(["uv", "pip", "freeze", "--python", str(python)]))
    sh(cmd, out / "sru.log", cwd=repo)
    sh([str(python), str(HERE / "examples.py"), str(out), "--n", str(args.examples)], cwd=repo)
    print((out / "report.md").read_text())
    if args.limit:
        print(f"first {args.limit} items only: not comparable with the published rates")
    print(f"run directory: {out}")


if __name__ == "__main__":
    main(tyro.cli(Args))
