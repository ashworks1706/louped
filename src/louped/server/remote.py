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
import re
import secrets
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.background import BackgroundTask

import louped
from louped import __version__, sync
from louped.core import experiments_dir
from louped.core.project import FILE
from louped.core.project import root as root_of_project
from louped.server.launch import Job, Jobs, Launchable, LaunchRequest, argv, require_json
from louped.stores.experiments import declared_extras
from louped.sync import Added, add_bundle

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
# louped job {job_id}: {title}. Run with `{run}`.
{usage}set -euo pipefail
ROOT="${{SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}}{folder}"
mkdir -p "$ROOT"
cd "$ROOT"
mkdir -p out
export LOUPED_HOME="$ROOT/out" INSPECT_LOG_DIR="$ROOT/out/logs"
export LOUPED_EXPERIMENTS="$ROOT/experiments"
export PYTHONUNBUFFERED=1
# uv's 30 s default times out on torch's and CUDA's wheels over a busy cluster link
export UV_HTTP_TIMEOUT="${{UV_HTTP_TIMEOUT:-300}}"
{cache}{remote}
command -v uv >/dev/null || {{ curl -LsSf https://astral.sh/uv/install.sh | sh; }}
export PATH="$HOME/.local/bin:$PATH"
{fetch}{install}
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
{push}tar -czf "louped-result-{job_id}.tar.gz" --exclude=out/vendor out  # vendor: tool environments
echo "Done ($code). Bring $ROOT/louped-result-{job_id}.tar.gz back and import it from louped's"
echo "Runs page, or run: louped import louped-result-{job_id}.tar.gz"
exit "$code"
"""

#: With a remote, the job pushes its results there and packs them only if that fails.
PUSH = """if louped push --result out/result.json; then
  echo "Done ($code). Results pushed to $LOUPED_REMOTE: Pull on louped's Runs page, or louped pull."
  exit "$code"
fi
echo "Pushing failed (above), so the result is packed to bring back by hand."
"""

#: A one-file job gets the project from git at the exported commit.
FETCH = """[ -d repo ] || git clone --quiet {url} repo
git -C repo fetch --quiet
git -C repo checkout --quiet --detach {commit}
"""

README = """louped job {job_id}: {title}

1. Copy this folder to {where}.
2. Run: {run}
3. {back}

The job installs its environment with uv{cache_note}. Gated Hugging Face models need HF_TOKEN set
before you run it{hf_push}. If compute nodes have no internet, run the install and model download
once on a login node first: the same commands as job.sh up to `source .venv/bin/activate`.
"""

#: What a remote URL may hold to go into job.sh as it is.
SAFE_URL = re.compile(r"^[\w.:/@+=~%-]+$")
#: Folders an export leaves out, ignored by git or not.
LEFT_OUT = {"__pycache__", ".venv", ".git", "out"}


@dataclass
class Clone:
    """Where a one-file job gets the project: a pushed commit of its git repository."""

    url: str
    commit: str
    top: Path


def _git(where: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True,
                          timeout=30)  # fmt: skip


def _clone(paths: list[Path]) -> Clone | str:
    """The pushed commit holding every path as it is here, or why there is none: a path outside
    the repository, a change not committed, or a commit not pushed."""
    if shutil.which("git") is None:
        return "git is not installed here"
    first = paths[0] if paths[0].is_dir() else paths[0].parent
    found = _git(first, "rev-parse", "--show-toplevel")
    if found.returncode != 0:
        return f"{first} is not in a git repository"
    top = Path(found.stdout.strip()).resolve()
    if outside := [p for p in paths if not p.resolve().is_relative_to(top)]:
        return f"{outside[0]} is outside {top.name}'s repository"
    status = _git(top, "status", "--porcelain=v1", "-z", "--ignored", "--", *map(str, paths))
    found_paths = _status_paths(status.stdout)
    changed = [p for p in found_paths if not LEFT_OUT & set(p.parts) and p.suffix != ".pyc"]
    if changed:
        more = f" (and {len(changed) - 1} more)" if len(changed) > 1 else ""
        return f"{changed[0]} is not committed{more}"
    commit = _git(top, "rev-parse", "HEAD").stdout.strip()
    branches = _git(top, "branch", "-r", "--contains", commit, "--format=%(refname:short)")
    pushed = [b for b in branches.stdout.split() if "/" in b and not b.endswith("/HEAD")]
    if not pushed:
        return "this commit is not pushed"
    url = _git(top, "remote", "get-url", pushed[0].split("/")[0]).stdout.strip()
    if urlsplit(url).password or (
        urlsplit(url).scheme.startswith("http") and urlsplit(url).username
    ):
        return "the git remote's URL holds credentials, which job.sh would carry"
    return Clone(url=url, commit=commit, top=top)


def _status_paths(out: str) -> list[Path]:
    """The paths in `git status --porcelain=v1 -z`: for a rename or copy, where it went."""
    entries = out.split("\0")
    paths: list[Path] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            paths.append(Path(entry[3:]))
            if entry[0] in "RC":
                i += 1  # the next entry is the old path
        i += 1
    return paths


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


def export(req: ExportRequest, jobs: Jobs, title: str) -> tuple[Path, str]:
    """What runs req on another machine, in a temporary folder, with a line saying what it does,
    and its job recorded as exported. One file, job.sh, when the project is a pushed git commit
    and louped is a release or in that repository; else a .tar.gz of job.sh and what it needs."""
    job_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    out = Path(tempfile.mkdtemp(prefix="louped-export-"))
    root = out / f"louped-{job_id}"
    (root / "job").mkdir(parents=True)
    target = req.target
    if target.extras is None:
        target = target.model_copy(update={"extras": _extras(req.id)})
    remote = sync.configured()
    # a folder on this machine is not reachable from the cluster: the job packs its result instead
    local = remote if remote is not None and sync.is_local(remote) else None
    remote = None if local else remote
    if remote is not None and not SAFE_URL.match(remote):
        raise ValueError(f"the remote {remote!r} has characters job.sh cannot carry")
    extras = [*(target.extras or []), *(["sync"] if remote else [])]
    header = _header(target, job_id)
    command = argv(req, root / "job", remote=True)
    project, source = root_of_project(), _checkout()
    needed = [p for p in (experiments_dir(), project and project / FILE) if p and p.exists()]
    needed += [source / n for n in ("pyproject.toml", "uv.lock", "src")] if source else []
    clone = _clone(needed) if needed else None
    if isinstance(clone, Clone) and (bad := _unsafe(root / "job")):
        clone = f"{bad} cannot go inside job.sh"
    flags = " ".join(f"--extra {e}" for e in extras)
    if source is None:
        spec = f"louped[{','.join(extras)}]=={__version__}"
        install = f"uv venv --allow-existing\nuv pip install {shlex.quote(spec)}"
    elif isinstance(clone, Clone):
        at = (Path("repo") / source.resolve().relative_to(clone.top)).as_posix()
        install = (
            f'UV_PROJECT_ENVIRONMENT="$ROOT/.venv" uv sync --locked --no-dev --project {at} {flags}'
        )
    else:
        install = f"uv sync --locked --no-dev {flags}"
    sol = target.provider == "sol"
    scratch = ('export HF_HOME="${HF_HOME:-/scratch/$USER/huggingface}"\n'
               'export UV_CACHE_DIR="${UV_CACHE_DIR:-/scratch/$USER/uv-cache}"\n')  # fmt: skip
    run = "bash job.sh" if target.provider == "shell" else "sbatch job.sh"
    host = {"sol": "sol", "slurm": "slurm", "shell": "vm"}[target.provider]
    where = {"sol": "Sol (scratch is a good place: /scratch/$USER)", "slurm": "the cluster",
             "shell": "the machine"}[target.provider]  # fmt: skip
    back = (f"Its results are pushed to {remote}: Pull on louped's Runs page." if remote else
            f"When it ends, bring back louped-result-{job_id}.tar.gz and import it on louped's "
            "Runs page (or `louped import` it).")  # fmt: skip
    parts = {"header": "\n".join(header), "job_id": job_id, "title": title, "run": run,
             "cache": scratch if sol else "", "command": shlex.join(command), "host": host,
             "remote": f'export LOUPED_REMOTE="${{LOUPED_REMOTE:-{remote}}}"\n' if remote else "",
             "push": PUSH if remote else "", "install": install}  # fmt: skip
    if isinstance(clone, Clone) or (clone is None and source is None):
        fetch = FETCH.format(url=shlex.quote(clone.url), commit=clone.commit) if clone else ""
        if clone and experiments_dir().is_dir():
            fetch += f"ln -sfn {_in_repo(experiments_dir(), clone)} experiments\n"
        if clone and project is not None:
            fetch += f"cp {_in_repo(project / FILE, clone)} {FILE}\n"
        fetch += _embedded(root / "job")
        usage = (f"# Copy it to {where} and run it there; it works in louped-{job_id}/ beside it.\n"
                 f"# {back}\n")  # fmt: skip
        script = SCRIPT.format(**parts, usage=usage, folder=f"/louped-{job_id}", fetch=fetch)
        job = out / f"louped-{job_id}.sh"
        job.write_text(script, encoding="utf-8")
        job.chmod(0o755)
        shutil.rmtree(root)
        note = f"One file: run it there with {run}. " + back
    else:
        _bundle(root, project)
        script = SCRIPT.format(**parts, usage="# See README.txt.\n", folder="", fetch="")
        (root / "job.sh").write_text(script, encoding="utf-8")
        (root / "job.sh").chmod(0o755)
        cache_note = ", caching it and models under /scratch/$USER" if sol else ""
        hf_push = (
            ", and so does pushing to an hf:// remote"
            if remote and remote.startswith("hf:")
            else ""
        )
        (root / "README.txt").write_text(README.format(job_id=job_id, title=title, where=where,
                                                       run=run, cache_note=cache_note, back=back,
                                                       hf_push=hf_push))  # fmt: skip
        manifest = {"job": job_id, "title": title, "argv": command, "target": target.model_dump(),
                    "louped": __version__, "request": req.model_dump(exclude={"target"}),
                    "skipped": _skipped(root)}  # fmt: skip
        (root / "louped.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        job = out / f"louped-{job_id}.tar.gz"
        with tarfile.open(job, "w:gz") as tar:
            tar.add(root, arcname=root.name)
        shutil.rmtree(root)
        why = f" ({clone})" if clone else ""
        note = f"A folder, not one file{why}: copy it there and run {run}. " + back
    if local:
        note += f" The remote {local} is a folder here, which the job cannot reach."
    jobs.record(Job(id=job_id, title=f"{title} · {host}", argv=command, status="exported"))
    return job, note


def _in_repo(path: Path, clone: Clone) -> str:
    return shlex.quote((Path("repo") / path.resolve().relative_to(clone.top)).as_posix())


def _unsafe(job_dir: Path) -> str | None:
    """A config under job/ a heredoc cannot carry as it is, if any."""
    for path in sorted(job_dir.iterdir()):
        text = path.read_text(encoding="utf-8")
        if "LOUPED_FILE" in text or not SAFE_URL.match(path.name):
            return f"job/{path.name}"
    return None


def _embedded(job_dir: Path) -> str:
    """The edited configs under job/ written out by job.sh itself."""
    files = sorted(job_dir.iterdir())
    lines = ["mkdir -p job\n"] if files else []
    for path in files:
        text = path.read_text(encoding="utf-8")
        end = "" if text.endswith("\n") else "\n"
        lines.append(f"cat > job/{path.name} <<'LOUPED_FILE'\n{text}{end}LOUPED_FILE\n")
    return "".join(lines)


def _bundle(root: Path, project: Path | None) -> None:
    """The experiments, project file and louped source a folder export carries."""
    skipped: list[str] = []

    def keep(src: str, names: list[str]) -> set[str]:
        drop = {n for n in names if n in LEFT_OUT}
        for n in names:
            path = Path(src, n)
            if path.is_file() and path.stat().st_size > MAX_FILE:
                drop.add(n)
                skipped.append(path.relative_to(experiments_dir()).as_posix())
        return drop

    if experiments_dir().is_dir():
        shutil.copytree(experiments_dir(), root / "experiments", ignore=keep)
    if project is not None:  # its domains, so its experiments read there
        shutil.copy2(project / FILE, root / FILE)
    if (source := _checkout()) is not None:
        for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", ".python-version"):
            if (source / name).exists():
                shutil.copy2(source / name, root / name)
        shutil.copytree(source / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".skipped").write_text("\n".join(skipped), encoding="utf-8")


def _skipped(root: Path) -> list[str]:
    marker = root / ".skipped"
    found = [x for x in marker.read_text(encoding="utf-8").splitlines() if x]
    marker.unlink()
    return found


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
        added = add_bundle(out)
        job = _finish(jobs, added.result, out) if jobs is not None else None
    return _imported_as(added, job)


def _imported_as(added: Added, job: str | None) -> Imported:
    return Imported(job=job, host=added.host, exit_code=int(added.result["exit_code"]),
                    runs=added.runs, skipped=added.skipped)  # fmt: skip


def pull_results(jobs: Jobs | None, url: str | None = None) -> list[Imported]:
    """Pull the remote's new bundles; one a job exported from here pushed finishes that job."""
    found: list[Imported] = []

    def finish(added: Added, out: Path) -> None:
        job = _finish(jobs, added.result, out) if jobs is not None else None
        found.append(_imported_as(added, job))

    sync.pull(url, finish)
    return found


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
    """Export, import, push and pull on the launch router: all write to this machine or the
    remote, so all are off with --expose, like launching."""

    @api.post("/export", dependencies=[Depends(require_json)])
    def export_job(req: ExportRequest) -> FileResponse:
        try:
            job, note = export(req, queue(), known(req.id).title)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        kind = "application/gzip" if job.suffix == ".gz" else "text/x-shellscript"
        # what the download is and does, for the UI to say; headers are latin-1
        said = {"x-louped-note": note.encode("ascii", "replace").decode()}
        return FileResponse(job, media_type=kind, filename=job.name, headers=said,
                            background=BackgroundTask(shutil.rmtree, job.parent))  # fmt: skip

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

    @api.post("/push", dependencies=[Depends(require_json)])
    async def push() -> sync.Pushed:
        queue()
        return await run_in_threadpool(_remote, sync.push)

    @api.post("/pull", dependencies=[Depends(require_json)])
    async def pull() -> list[Imported]:
        jobs = queue()
        return await run_in_threadpool(_remote, lambda: pull_results(jobs))

    @api.post("/import-path", dependencies=[Depends(require_json)])
    async def import_path(req: ImportPath) -> Imported:
        path = Path(req.path).expanduser()
        if not path.exists():
            raise HTTPException(400, f"{path} does not exist")
        return await run_in_threadpool(_imported, path, queue())


def _remote[T](call: Callable[[], T]) -> T:
    """A push or pull, with a missing or unreachable remote said as a 400, not a crash."""
    try:
        return call()
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _imported(path: Path, jobs: Jobs) -> Imported:
    try:
        return import_result(path, jobs)
    except (ValueError, tarfile.TarError, KeyError) as exc:
        raise HTTPException(400, f"not a louped result: {exc}") from exc
