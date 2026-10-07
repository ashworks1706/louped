"""Running a launch on another machine: ASU's Sol, any Slurm cluster, a plain VM, or Colab.

Export writes a bundle for one launch: job.sh (the scheduler's header, environment setup with uv,
then the same command the Launch form would run here), the experiments/ folder, any edited config
under job/, the project to install, and louped.json naming the job. On the other machine, job.sh
writes everything under out/ as a louped home of its own (Inspect logs, MLflow, artifacts) with
out/result.json and out/log.txt, and packs out/ as louped-result-<id>.tar.gz. For Colab, the export
is a notebook that writes that one-file job.sh, runs it, and downloads the result.

Import reads that archive, or the folder it unpacks to: eval logs are copied into the local logs,
MLflow runs re-logged into the local store with their metrics, params, tags and artifacts, every run
recorded with the host it ran on, and the exported job takes the result's exit code and log. A run
imported twice is skipped the second time. An archive is unpacked under <home>/staging, on the
stores' disk and not in /tmp, once its unpacked size is known to fit, and moved in from there; a
folder is read where it is.
"""

from __future__ import annotations

import json
import re
import secrets
import shlex
import shutil
import tarfile
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import nbformat
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.background import BackgroundTask

import louped
from louped import __version__, sync
from louped.core import experiments_dir, home, require_space
from louped.core.git import git, pushed_to
from louped.core.git import top as repo_top
from louped.core.project import FILE
from louped.core.project import root as root_of_project
from louped.server.launch import Job, Jobs, Launchable, LaunchRequest, argv, require_json
from louped.stores.experiments import declared_extras
from louped.sync import Added, add_bundle

Provider = Literal["sol", "slurm", "shell", "colab"]
#: Sol's GPUs as its docs name them for -G: MI200 is AMD (ROCm), the slices are A100 MIG.
SOL_GPUS = ["a100", "a30", "h100", "mi200", "1g.20gb", "2g.20gb"]
EXTRAS = ["interp", "evals", "tracking", "train", "rl", "rag", "sae", "data"]
#: What a job installs when neither the form nor the experiment says.
DEFAULT_EXTRAS = ["interp", "evals", "tracking", "train"]
#: What `uv sync` needs beside src/ to build louped from a checkout: pyproject.toml names the
#: readme and license, and its wheel's build hook is hatch_build.py.
BUILD = ("pyproject.toml", "uv.lock", "hatch_build.py", "README.md", "LICENSE", ".python-version")
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
    if target.provider in ("shell", "colab"):
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
{token}started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
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
{hint}exit "$code"
"""

#: With a remote, the job pushes its results there and packs them only if that fails.
PUSH = """if louped push --result out/result.json; then
  echo "Done ($code). Results pushed to $LOUPED_REMOTE: Pull on louped's Runs page, or louped pull."
  exit "$code"
fi
echo "Pushing failed (above), so the result is packed to bring back by hand."
"""

#: Without a remote: big results belong in storage, not on a laptop.
LARGE = "For large results, set a remote in louped.toml so the job pushes them straight to storage."

#: An hf:// remote: say a missing token before the run, not after it.
TOKEN = """python -c 'import huggingface_hub as h, sys; sys.exit(h.get_token() is None)' || {
  echo "No Hugging Face token here, which pushing to $LOUPED_REMOTE needs:"
  echo "run hf auth login once on this machine, or set HF_TOKEN."; exit 1; }
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
before you run it. If compute nodes have no internet, run the install and model download
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


def _clone(paths: list[Path]) -> Clone | str:
    """The pushed commit holding every path as it is here, or why there is none: a path outside
    the repository, a change not committed, or a commit not pushed."""
    if shutil.which("git") is None:
        return "git is not installed here"
    first = paths[0] if paths[0].is_dir() else paths[0].parent
    top = repo_top(first)
    if top is None:
        return f"{first} is not in a git repository"
    if outside := [p for p in paths if not p.resolve().is_relative_to(top)]:
        return f"{outside[0]} is outside {top.name}'s repository"
    status = git(top, "status", "--porcelain=v1", "-z", "--ignored", "--", *map(str, paths))
    found_paths = _status_paths(status.stdout)
    changed = [p for p in found_paths if not LEFT_OUT & set(p.parts) and p.suffix != ".pyc"]
    if changed:
        more = f" (and {len(changed) - 1} more)" if len(changed) > 1 else ""
        return f"{changed[0]} is not committed{more}"
    commit = git(top, "rev-parse", "HEAD").stdout.strip()
    pushed = pushed_to(top, commit)
    if not pushed:
        return "this commit is not pushed"
    url = git(top, "remote", "get-url", pushed[0].split("/")[0]).stdout.strip()
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
    and louped is a release or in that repository; else a .tar.gz of job.sh and what it needs.
    For Colab, a notebook running that one file; ValueError when the project is not pushed."""
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
    # the cache moves to scratch; the token stays where `hf auth login` on the cluster put it
    token = "${HF_HOME:-$HOME/.cache/huggingface}/token"
    scratch = (f'export HF_TOKEN_PATH="${{HF_TOKEN_PATH:-{token}}}"\n'
               'export HF_HOME="${HF_HOME:-/scratch/$USER/huggingface}"\n'
               'export UV_CACHE_DIR="${UV_CACHE_DIR:-/scratch/$USER/uv-cache}"\n')  # fmt: skip
    colab = target.provider == "colab"
    pushed = clone if isinstance(clone, Clone) else None
    one_file = pushed is not None or (clone is None and source is None)
    if colab and not one_file:
        shutil.rmtree(out)
        raise ValueError("Colab gets the project with git, so it must be a pushed commit: "
                         f"{clone}. Commit and push it, then export again.")  # fmt: skip
    run = "sbatch job.sh" if target.provider in ("sol", "slurm") else "bash job.sh"
    host = {"sol": "sol", "slurm": "slurm", "shell": "vm", "colab": "colab"}[target.provider]
    where = {"sol": "Sol (scratch is a good place: /scratch/$USER)", "slurm": "the cluster",
             "shell": "the machine", "colab": "Colab"}[target.provider]  # fmt: skip
    back = (f"Its results are pushed to {remote}: Pull on louped's Runs page." if remote else
            f"When it ends, the last cell downloads louped-result-{job_id}.tar.gz: import it on "
            "louped's Runs page." if colab else
            f"When it ends, bring back louped-result-{job_id}.tar.gz and import it on louped's "
            f"Runs page (or `louped import` it). {LARGE}")  # fmt: skip
    if remote and sync.bucket(remote):
        back += (" Pushing there needs a Hugging Face token: the HF_TOKEN secret in Colab." if colab
                 else " Pushing there needs a Hugging Face token: run hf auth login once on that "
                 "machine.")  # fmt: skip
    parts = {"header": "\n".join(header), "job_id": job_id, "title": title, "run": run,
             "cache": scratch if sol else "", "command": shlex.join(command), "host": host,
             "remote": f'export LOUPED_REMOTE="${{LOUPED_REMOTE:-{remote}}}"\n' if remote else "",
             "push": PUSH if remote else "", "install": install,
             "hint": "" if remote else f'echo "{LARGE}"\n',
             "token": TOKEN if remote and sync.bucket(remote) else ""}  # fmt: skip
    if one_file:
        fetch = FETCH.format(url=shlex.quote(pushed.url), commit=pushed.commit) if pushed else ""
        if pushed and experiments_dir().is_dir():
            fetch += f"ln -sfn {_in_repo(experiments_dir(), pushed)} experiments\n"
        if pushed and project is not None:
            fetch += f"cp {_in_repo(project / FILE, pushed)} {FILE}\n"
        fetch += _embedded(root / "job")
        usage = (
            f"# Copy it to {where} and run it there; it works in louped-{job_id}/ beside it.\n"
            if not colab
            else "# The notebook writes and runs this file.\n"
        ) + f"# {back}\n"
        script = SCRIPT.format(**parts, usage=usage, folder=f"/louped-{job_id}", fetch=fetch)
        shutil.rmtree(root)
        if colab:
            job = out / f"louped-{job_id}.ipynb"
            at = pushed.commit if pushed else None
            nb = notebook(script, job_id, title, shlex.join(command), at, remote)
            nbformat.write(nb, str(job))
            note = ("A notebook: open it in Colab (File > Upload notebook), pick a GPU runtime "
                    "and run all. " + back)  # fmt: skip
        else:
            job = out / f"louped-{job_id}.sh"
            job.write_text(script, encoding="utf-8")
            job.chmod(0o755)
            note = f"One file: run it there with {run}. " + back
    else:
        _bundle(root, project)
        script = SCRIPT.format(**parts, usage="# See README.txt.\n", folder="", fetch="")
        (root / "job.sh").write_text(script, encoding="utf-8")
        (root / "job.sh").chmod(0o755)
        cache_note = ", caching it and models under /scratch/$USER" if sol else ""
        readme = README.format(job_id=job_id, title=title, where=where, run=run,
                               cache_note=cache_note, back=back)  # fmt: skip
        (root / "README.txt").write_text(readme)
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


COLAB_INTRO = """# louped job {job_id}: {title}

This notebook runs `{command}` from {source} on a Colab GPU. Its results come back to louped.

1. Pick a GPU runtime: **Runtime > Change runtime type**, then a GPU (a T4 is free).
2. Gated Hugging Face models{push} need a token. Add it as the secret `HF_TOKEN`: the key icon on
   the left. Allow this notebook to read it.
3. Run all: **Runtime > Run all**. {back}
"""

#: The Hugging Face token from Colab's secrets, never from the notebook itself.
COLAB_TOKEN = """import os

from google.colab import userdata

try:
    os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")
    print("HF_TOKEN is set from this notebook's secrets.")
except (userdata.SecretNotFoundError, userdata.NotebookAccessError):
    {missing}(
        "No HF_TOKEN secret, or this notebook may not read it. {need} Add HF_TOKEN under "
        "Secrets (the key icon on the left), allow this notebook, and run this cell again."
    )
"""

#: job.sh with its output shown as it runs; its exit code said, not raised, so the result cell runs.
COLAB_RUN = """import subprocess

job = subprocess.Popen(["bash", "job.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True)
for line in job.stdout:
    print(line, end="")
code = job.wait()
print(f"job.sh ended with exit code {code}." if code else "job.sh succeeded.")
"""

COLAB_DOWNLOAD = """from google.colab import files

files.download("louped-{job_id}/louped-result-{job_id}.tar.gz")
"""

#: With a remote, the result is packed only when pushing it failed.
COLAB_PUSHED = """from pathlib import Path

archive = Path("louped-{job_id}/louped-result-{job_id}.tar.gz")
if archive.exists():  # pushing failed (above): bring the result back by hand
    from google.colab import files

    files.download(str(archive))
else:
    print("The results are pushed to {remote}: Pull on louped's Runs page.")
"""


def notebook(script: str, job_id: str, title: str, command: str, commit: str | None,
             remote: str | None) -> nbformat.NotebookNode:  # fmt: skip
    """A Colab notebook that runs a one-file job.sh: it writes it, sets the Hugging Face token
    from Colab's secrets, runs it, and downloads the result (or says it was pushed)."""
    v4 = nbformat.v4
    source = f"the project at commit `{commit[:12]}`" if commit else f"louped {__version__}"
    bucket = remote is not None and sync.bucket(remote)
    back = (f"The job pushes its results to `{remote}`: then Pull on louped's Runs page." if remote
            else f"The last cell downloads `louped-result-{job_id}.tar.gz`: import it on "
            "louped's Runs page.")  # fmt: skip
    intro = COLAB_INTRO.format(job_id=job_id, title=title, command=command, source=source,
                               push=", and pushing the results," if bucket else "",
                               back=back)  # fmt: skip
    need = ("Pushing the results needs it." if bucket else
            "Only gated models need it; the job goes on without.")  # fmt: skip
    token = COLAB_TOKEN.format(missing="raise RuntimeError" if bucket else "print", need=need)
    result = (COLAB_PUSHED.format(job_id=job_id, remote=remote) if remote else
              COLAB_DOWNLOAD.format(job_id=job_id))  # fmt: skip
    cells = [v4.new_markdown_cell(intro), v4.new_code_cell(token),
             v4.new_code_cell(f"%%writefile job.sh\n{script}"), v4.new_code_cell(COLAB_RUN),
             v4.new_code_cell(result)]  # fmt: skip
    meta = {"accelerator": "GPU", "colab": {"provenance": []},
            "kernelspec": {"name": "python3", "display_name": "Python 3"}}  # fmt: skip
    nb = v4.new_notebook(cells=cells, metadata=meta)
    nbformat.validate(nb)
    return nb


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
        for name in BUILD:
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
    """Add a result archive's (or unpacked folder's) runs to the local stores. A folder is copied
    in from where it is; an archive is unpacked under <home>/staging and moved in."""
    if path.is_dir():
        out = _out(path)
        require_space(sum(p.stat().st_size for p in out.rglob("*") if p.is_file()), home())
        added = add_bundle(out)
        job = _finish(jobs, added.result, out) if jobs is not None else None
        return _imported_as(added, job)
    if not tarfile.is_tarfile(path):
        raise ValueError(f"{path} is not a louped result archive or folder")
    with sync.staging() as tmp, tarfile.open(path) as tar:
        # its unpacked size from the members' headers, before anything is written
        require_space(sum(m.size for m in tar if m.isfile()), tmp)
        tar.extractall(tmp, filter="data")  # refuses absolute paths and ../
        out = _out(tmp)
        added = add_bundle(out, move=True)
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


class Connect(BaseModel):
    #: The remote to set in louped.toml; empty for a private HF bucket of the signed-in account.
    remote: str = ""
    #: A Hugging Face token, kept where `hf auth login` keeps it; empty to use the one there.
    token: str = ""


class RemoteState(BaseModel):
    remote: str | None
    #: Whether a Hugging Face token is on this machine, which an hf:// remote needs.
    token: bool


def routes(api: APIRouter, queue: Callable[[], Jobs], known: Callable[[str], Launchable]) -> None:
    """Export, import, push and pull on the launch router: all write to this machine or the
    remote, so all are off with --expose, like launching."""

    @api.post("/export", dependencies=[Depends(require_json)])
    def export_job(req: ExportRequest) -> FileResponse:
        try:
            job, note = export(req, queue(), known(req.id).title)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        kind = {".gz": "application/gzip", ".ipynb": "application/x-ipynb+json"}.get(
            job.suffix, "text/x-shellscript"
        )
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
        with sync.staging() as tmp:  # on the stores' disk: a result can be bigger than /tmp
            path = tmp / "result.tar.gz"
            if size := request.headers.get("content-length", "").strip():
                try:
                    require_space(int(size), tmp)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
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

    @api.post("/remote", dependencies=[Depends(require_json)])
    async def connect(req: Connect) -> RemoteState:
        queue()

        def setup() -> RemoteState:
            if req.token.strip():
                sync.save_token(req.token.strip())
            url = req.remote.strip() or sync.suggested()
            if url is None:
                raise sync.NeedsToken("a Hugging Face token is needed for a bucket of your own")
            sync.ready(url, create=True)
            sync.set_remote(url)
            return RemoteState(remote=sync.configured(), token=sync.has_token())

        return await run_in_threadpool(_remote, setup)

    @api.post("/import-path", dependencies=[Depends(require_json)])
    async def import_path(req: ImportPath) -> Imported:
        path = Path(req.path).expanduser()
        if not path.exists():
            raise HTTPException(400, f"{path} does not exist")
        return await run_in_threadpool(_imported, path, queue())


def _remote[T](call: Callable[[], T]) -> T:
    """A push or pull, with a missing or unreachable remote said as a 400, not a crash, and a
    missing Hugging Face token as a 401, for the app to ask for one."""
    try:
        return call()
    except sync.NeedsToken as exc:
        raise HTTPException(401, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _imported(path: Path, jobs: Jobs) -> Imported:
    try:
        return import_result(path, jobs)
    except (tarfile.TarError, KeyError) as exc:
        raise HTTPException(400, f"not a louped result: {exc}") from exc
    except ValueError as exc:  # not a result, or no room for it: each says which
        raise HTTPException(400, str(exc)) from exc
