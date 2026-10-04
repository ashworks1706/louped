"""Running a launch on another machine: ASU's Sol, any Slurm cluster, or a plain VM.

Export writes a bundle for one launch: job.sh (the scheduler's header, environment setup with uv,
then the same command the Launch form would run here), the experiments/ folder, any edited config
under job/, the project to install, and louped.json naming the job. On the other machine, job.sh
writes everything under out/ as a louped home of its own (Inspect logs, MLflow, artifacts) with
out/result.json and out/log.txt, and packs out/ as louped-result-<id>.tar.gz.

Import reads that archive, or the folder it unpacks to: eval logs are copied into the local logs,
MLflow runs re-logged into the local store with their metrics, params, tags and artifacts, every run
recorded with the host it ran on, and the exported job takes the result's exit code and log. A run
imported twice is skipped the second time.
"""

from __future__ import annotations

import json
import secrets
import shlex
import shutil
import tarfile
import tempfile
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.background import BackgroundTask

import louped
from louped import __version__
from louped.core import experiments_dir, home, logs_dir, tracking_uri
from louped.core.project import FILE
from louped.core.project import root as root_of_project
from louped.server.launch import Job, Jobs, Launchable, LaunchRequest, argv, require_json
from louped.stores.experiments import declared_extras

Provider = Literal["sol", "slurm", "shell"]
#: Sol's GPUs as its docs name them for -G: MI200 is AMD (ROCm), the slices are A100 MIG.
SOL_GPUS = ["a100", "a30", "h100", "mi200", "1g.20gb", "2g.20gb"]
EXTRAS = ["interp", "evals", "tracking", "train", "rl", "rag", "sae", "data"]
#: What a job installs when neither the form nor the experiment says.
DEFAULT_EXTRAS = ["interp", "evals", "tracking", "train"]
#: Files under experiments/ bigger than this stay behind; louped.json lists them.
MAX_FILE = 50 * 2**20
SAFE = r"^[\w.:-]+$"


class Target(BaseModel):
    """Where and on what an exported job runs."""

    provider: Provider = "sol"
    #: Sol: a100, a30, h100, mi200, 1g.20gb or 2g.20gb. Slurm: a gres type, or none for any.
    gpu: str | None = Field(default="a100", pattern=SAFE)
    gpus: int = Field(default=1, ge=0, le=8)
    hours: int = Field(default=4, ge=1, le=168)
    cpus: int = Field(default=8, ge=1, le=128)
    #: Sol: public, or highmem over 512 GiB. Defaults to public on Sol, the cluster's own else.
    partition: str | None = Field(default=None, pattern=SAFE)
    #: Sol: public, or a lab's grp_ QOS.
    qos: str | None = Field(default=None, pattern=SAFE)
    #: A node feature, such as Sol's a100_80 for the 80 GB A100.
    constraint: str | None = Field(default=None, pattern=SAFE)
    #: The package extras the job installs: these; else what the experiment's README declares
    #: (`extras:` in its front matter); else DEFAULT_EXTRAS.
    extras: list[str] | None = None

    @field_validator("extras")
    @classmethod
    def _known(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (unknown := set(value) - set(EXTRAS)):
            raise ValueError(f"unknown extras {sorted(unknown)}; one of {EXTRAS}")
        return value


class ExportRequest(LaunchRequest):
    target: Target = Field(default_factory=Target)


class Imported(BaseModel):
    job: str | None = Field(description="The exported job the result answers, when known here.")
    host: str
    exit_code: int
    runs: list[str] = Field(description="Runs added to the local stores.")
    skipped: list[str] = Field(description="Runs already imported.")


def _header(target: Target, job_id: str) -> list[str]:
    if target.provider == "shell":
        return []
    lines = [f"-J louped-{job_id}", f"-o louped-{job_id}.%j.out", f"-t {target.hours}:00:00",
             f"-c {target.cpus}"]  # fmt: skip
    partition = target.partition or ("public" if target.provider == "sol" else None)
    qos = target.qos or ("public" if target.provider == "sol" else None)
    lines += [f"-p {partition}"] if partition else []
    lines += [f"-q {qos}"] if qos else []
    if target.gpus:
        if target.provider == "sol":
            if target.gpu not in SOL_GPUS:
                raise ValueError(f"Sol's GPUs are {SOL_GPUS}")
            lines.append(f"-G {target.gpu}:{target.gpus}")
        else:
            kind = f"{target.gpu}:" if target.gpu else ""
            lines.append(f"--gres=gpu:{kind}{target.gpus}")
    lines += [f"-C {target.constraint}"] if target.constraint else []
    return [f"#SBATCH {line}" for line in lines]


def _checkout() -> Path | None:
    """The louped source this server runs from (src/louped in a checkout with its uv.lock), so the
    job installs exactly this code; None for an installed release."""
    source = Path(louped.__file__).resolve().parents[2]
    pyproject = source / "pyproject.toml"
    if not pyproject.exists() or not (source / "uv.lock").exists():
        return None
    name = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("name")
    return source if name == "louped" else None


SCRIPT = """#!/bin/bash
{header}
# louped job {job_id}: {title}. Run with `{run}`; see README.txt.
set -euo pipefail
ROOT="${{SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}}"
cd "$ROOT"
mkdir -p out
export LOUPED_HOME="$ROOT/out" INSPECT_LOG_DIR="$ROOT/out/logs"
export LOUPED_EXPERIMENTS="$ROOT/experiments"
export PYTHONUNBUFFERED=1
# uv's 30 s default times out on torch's and CUDA's wheels over a busy cluster link
export UV_HTTP_TIMEOUT="${{UV_HTTP_TIMEOUT:-300}}"
{cache}
command -v uv >/dev/null || {{ curl -LsSf https://astral.sh/uv/install.sh | sh; }}
export PATH="$HOME/.local/bin:$PATH"
{install}
source .venv/bin/activate
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
set +e
{command} 2>&1 | tee out/log.txt
code=${{PIPESTATUS[0]}}
set -e
python - "$code" "$started" "$ROOT/out" <<'PY'
import json, shutil, socket, subprocess, sys
from datetime import UTC, datetime
gpu = ""
if shutil.which("nvidia-smi"):
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip().replace("\\n", ", ")
json.dump({{"job": "{job_id}", "host": "{host}", "node": socket.gethostname(), "gpu": gpu,
           "exit_code": int(sys.argv[1]), "started": sys.argv[2],
           "ended": datetime.now(UTC).isoformat(), "home": sys.argv[3]}},
          open("out/result.json", "w"), indent=2)
PY
tar -czf "louped-result-{job_id}.tar.gz" --exclude=out/vendor out  # vendor: tool environments
echo "Done ($code). Bring louped-result-{job_id}.tar.gz back and import it from louped's Runs page,"
echo "or run: louped import louped-result-{job_id}.tar.gz"
exit "$code"
"""

README = """louped job {job_id}: {title}

1. Copy this folder to {where}.
2. Run: {run}
3. When it ends, bring back louped-result-{job_id}.tar.gz and import it from louped's Runs page
   (or run `louped import louped-result-{job_id}.tar.gz` where louped runs).

The job installs its environment with uv{cache_note}. Gated Hugging Face models need HF_TOKEN set
before you run it. If compute nodes have no internet, run the install and model download once on
a login node first: the same commands as job.sh up to `source .venv/bin/activate`.
"""


def _extras(launchable: str) -> list[str]:
    """The extras for a launch: its experiment's declared ones for a script, else the defaults."""
    if not launchable.startswith("script:"):
        return DEFAULT_EXTRAS
    name = launchable.removeprefix("script:").split("/")[0]
    declared = declared_extras(name)
    if declared is None:
        return DEFAULT_EXTRAS
    if unknown := set(declared) - set(EXTRAS):
        raise ValueError(f"experiments/{name}/README.md: unknown extras {sorted(unknown)}; "
                         f"one of {EXTRAS}")  # fmt: skip
    return declared


def export(req: ExportRequest, jobs: Jobs, title: str) -> Path:
    """The bundle for req as a .tar.gz in a temporary folder, and its job recorded as exported."""
    job_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    out = Path(tempfile.mkdtemp(prefix="louped-export-"))
    root = out / f"louped-{job_id}"
    (root / "job").mkdir(parents=True)
    target = req.target
    if target.extras is None:
        target = target.model_copy(update={"extras": _extras(req.id)})
    header = _header(target, job_id)
    command = argv(req, root / "job", remote=True)
    skipped: list[str] = []

    def keep(src: str, names: list[str]) -> set[str]:
        drop = {n for n in names if n in ("__pycache__", ".venv", ".git", "out")}
        for n in names:
            path = Path(src, n)
            if path.is_file() and path.stat().st_size > MAX_FILE:
                drop.add(n)
                skipped.append(path.relative_to(experiments_dir()).as_posix())
        return drop

    if experiments_dir().is_dir():
        shutil.copytree(experiments_dir(), root / "experiments", ignore=keep)
    if (project := root_of_project()) is not None:  # its domains, so its experiments read there
        shutil.copy2(project / FILE, root / FILE)
    extras = " ".join(f"--extra {e}" for e in target.extras or [])
    if (source := _checkout()) is not None:
        for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", ".python-version"):
            if (source / name).exists():
                shutil.copy2(source / name, root / name)
        shutil.copytree(source / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        install = f"uv sync --locked --no-dev {extras}"
    else:
        spec = f"louped[{','.join(target.extras or [])}]=={__version__}"
        install = f"uv venv --allow-existing\nuv pip install {shlex.quote(spec)}"
    sol = target.provider == "sol"
    scratch = ('export HF_HOME="${HF_HOME:-/scratch/$USER/huggingface}"\n'
               'export UV_CACHE_DIR="${UV_CACHE_DIR:-/scratch/$USER/uv-cache}"')  # fmt: skip
    cache = scratch if sol else ""
    run = "bash job.sh" if target.provider == "shell" else "sbatch job.sh"
    host = {"sol": "sol", "slurm": "slurm", "shell": "vm"}[target.provider]
    script = SCRIPT.format(header="\n".join(header), job_id=job_id, title=title, run=run,
                           cache=cache, install=install, command=shlex.join(command),
                           host=host)  # fmt: skip
    (root / "job.sh").write_text(script, encoding="utf-8")
    (root / "job.sh").chmod(0o755)
    where = {"sol": "Sol (scratch is a good place: /scratch/$USER)", "slurm": "the cluster",
             "shell": "the machine"}[target.provider]  # fmt: skip
    cache_note = ", caching it and models under /scratch/$USER" if sol else ""
    (root / "README.txt").write_text(README.format(job_id=job_id, title=title, where=where,
                                                   run=run, cache_note=cache_note))  # fmt: skip
    manifest = {"job": job_id, "title": title, "argv": command, "target": target.model_dump(),
                "louped": __version__, "request": req.model_dump(exclude={"target"}),
                "skipped": skipped}  # fmt: skip
    (root / "louped.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive = out / f"louped-{job_id}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=root.name)
    shutil.rmtree(root)
    jobs.record(Job(id=job_id, title=f"{title} · {host}", argv=command, status="exported"))
    return archive


def _out(folder: Path) -> Path:
    """The out/ folder of an unpacked result: the folder itself or one below it."""
    for candidate in (folder, folder / "out", *folder.glob("*/out")):
        if (candidate / "result.json").exists():
            return candidate
    raise ValueError(f"no louped result in {folder}: expected out/result.json")


def import_result(path: Path, jobs: Jobs | None) -> Imported:
    """Add a result archive's (or unpacked folder's) runs to the local stores."""
    with tempfile.TemporaryDirectory() as tmp:
        if path.is_dir():
            out = _out(path)
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as tar:
                tar.extractall(tmp, filter="data")  # refuses absolute paths and ../
            out = _out(Path(tmp))
        else:
            raise ValueError(f"{path} is not a louped result archive or folder")
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        host = str(result.get("host") or "remote")
        added, skipped = _evals(out, host)
        # the node and GPUs it ran on, for the run page's provenance
        where = {f"louped.{k}": str(result[k]) for k in ("node", "gpu") if result.get(k)}
        more, again = _mlflow(out, host, str(result.get("home", "")), where)
        job = _finish(jobs, result, out) if jobs is not None else None
    return Imported(job=job, host=host, exit_code=int(result["exit_code"]), runs=added + more,
                    skipped=skipped + again)  # fmt: skip


def _evals(out: Path, host: str) -> tuple[list[str], list[str]]:
    from inspect_ai.log import read_eval_log

    added: list[str] = []
    skipped: list[str] = []
    found = sorted((out / "logs").glob("*.eval")) if (out / "logs").is_dir() else []
    logs_dir().mkdir(parents=True, exist_ok=True)
    for log in found:
        run_id = "e-" + read_eval_log(str(log), header_only=True).eval.eval_id
        if (logs_dir() / log.name).exists():
            skipped.append(run_id)
            continue
        shutil.copy2(log, logs_dir() / log.name)
        added.append(run_id)
    _record_hosts(dict.fromkeys(added, host))
    return added, skipped


def _record_hosts(hosts: dict[str, str]) -> None:
    """Remember where imported eval runs ran: Inspect logs carry no host of their own."""
    if not hosts:
        return
    path = home() / "hosts.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(known | hosts, indent=2, sort_keys=True), encoding="utf-8")


def _mlflow(
    out: Path, host: str, remote_home: str, where: dict[str, str]
) -> tuple[list[str], list[str]]:
    db = out / "mlflow.db"
    if not db.exists():
        return [], []
    from mlflow import MlflowClient
    from mlflow.entities import Metric, Param

    from louped.tracking.runs import experiment_id

    theirs = MlflowClient(tracking_uri=f"sqlite:///{db}")
    ours = MlflowClient(tracking_uri=tracking_uri())
    added: list[str] = []
    skipped: list[str] = []
    for experiment in theirs.search_experiments():
        for run in theirs.search_runs([experiment.experiment_id], max_results=10_000):
            origin = run.info.run_id
            seen = ours.search_runs(
                [e.experiment_id for e in ours.search_experiments()],
                filter_string=f"tags.`louped.imported_from` = '{origin}'",
            )
            if seen:
                skipped.append(f"m-{seen[0].info.run_id}")
                continue
            tags = {**run.data.tags, **where, "louped.host": host, "louped.imported_from": origin}
            new = ours.create_run(experiment_id(experiment.name), start_time=run.info.start_time,
                                  tags=tags, run_name=run.info.run_name)  # fmt: skip
            params = [Param(k, v) for k, v in run.data.params.items()]
            for i in range(0, len(params), 100):  # MLflow's batch limits
                ours.log_batch(new.info.run_id, params=params[i : i + 100])
            metrics = [Metric(m.key, m.value, m.timestamp, m.step) for key in run.data.metrics
                       for m in theirs.get_metric_history(origin, key)]  # fmt: skip
            for i in range(0, len(metrics), 1000):
                ours.log_batch(new.info.run_id, metrics=metrics[i : i + 1000])
            local = _artifacts(out, run.info.artifact_uri or "", remote_home)
            if local is not None and local.is_dir():
                ours.log_artifacts(new.info.run_id, str(local))
            ours.set_terminated(new.info.run_id, run.info.status, end_time=run.info.end_time)
            added.append(f"m-{new.info.run_id}")
    return added, skipped


def _artifacts(out: Path, uri: str, remote_home: str) -> Path | None:
    """A remote run's artifact folder inside the unpacked out/: its path under the remote home."""
    path = uri.removeprefix("file://")
    if remote_home and path.startswith(remote_home.rstrip("/") + "/"):
        return out / path[len(remote_home.rstrip("/")) + 1 :]
    return None


def _finish(jobs: Jobs, result: dict, out: Path) -> str | None:
    """The exported job takes the result's exit code, end and log; None when it is not ours."""
    job_id = str(result.get("job", ""))
    try:
        job = jobs.get(job_id)
    except HTTPException:  # exported from another louped: its runs are imported all the same
        return None
    log = out / "log.txt"
    if log.exists():
        shutil.copy2(log, jobs.dir / job_id / "log.txt")
    code = int(result["exit_code"])
    ended = datetime.fromisoformat(result["ended"]) if result.get("ended") else datetime.now(UTC)
    started = datetime.fromisoformat(result["started"].replace("Z", "+00:00"))
    status = "succeeded" if code == 0 else "failed"
    done = {"status": status, "exit_code": code, "started": started, "ended": ended}
    jobs.record(job.model_copy(update=done))
    return job_id


class ImportPath(BaseModel):
    #: A result archive or its unpacked folder on this machine, for results too big to upload.
    path: str


def routes(api: APIRouter, queue: Callable[[], Jobs], known: Callable[[str], Launchable]) -> None:
    """Export and import on the launch router: both write to this machine, so both are off with
    --expose, like launching."""

    @api.post("/export", dependencies=[Depends(require_json)])
    def export_job(req: ExportRequest) -> FileResponse:
        try:
            archive = export(req, queue(), known(req.id).title)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return FileResponse(archive, media_type="application/gzip", filename=archive.name,
                            background=BackgroundTask(shutil.rmtree, archive.parent))  # fmt: skip

    @api.post("/import")
    async def import_upload(request: Request) -> Imported:
        jobs = queue()
        kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind not in ("application/gzip", "application/x-gzip"):
            raise HTTPException(415, "send the result archive as application/gzip")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "result.tar.gz")
            with path.open("wb") as out:
                async for chunk in request.stream():
                    out.write(chunk)
            return await run_in_threadpool(_imported, path, jobs)

    @api.post("/import-path", dependencies=[Depends(require_json)])
    async def import_path(req: ImportPath) -> Imported:
        path = Path(req.path).expanduser()
        if not path.exists():
            raise HTTPException(400, f"{path} does not exist")
        return await run_in_threadpool(_imported, path, queue())


def _imported(path: Path, jobs: Jobs) -> Imported:
    try:
        return import_result(path, jobs)
    except (ValueError, tarfile.TarError, KeyError) as exc:
        raise HTTPException(400, f"not a louped result: {exc}") from exc
