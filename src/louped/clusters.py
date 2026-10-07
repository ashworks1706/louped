"""Clusters a project submits jobs to over ssh, named in its louped.toml:

    [clusters.sol]
    ssh = "sol"                  # a Host in ~/.ssh/config: keys, user, ControlMaster are its
    provider = "sol"             # sol | slurm | shell
    dir = "/scratch/$USER/louped"

Every call goes through ssh and scp in batch mode (no password prompt; louped stores none) with a
timeout, and a failure raises SshError carrying the command's stderr. A Slurm job is followed
with sacct; a shell job (nohup bash on a VM) with kill -0 on its process.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from louped.core.project import config

Provider = Literal["sol", "slurm", "shell"]
#: A Host as ssh takes it, never an option.
HOST = re.compile(r"^[\w][\w.@-]*$")
#: A folder the remote shell expands ($USER, ~), with nothing that could end the command.
DIR = re.compile(r"^[\w./~${}-]+$")
OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
#: Seconds a command over ssh, and a copy over scp, may take.
SSH_TIMEOUT = 60
COPY_TIMEOUT = 900
#: Slurm states of a job that has started and not ended; any state not here or in ENDED waits.
RUNNING = {"RUNNING", "COMPLETING", "CONFIGURING", "STAGE_OUT", "SIGNALING", "SUSPENDED"}
ENDED = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL",
         "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED", "ENDED"}  # fmt: skip


@dataclass(frozen=True)
class Cluster:
    name: str
    ssh: str
    provider: Provider
    dir: str


class SshError(RuntimeError):
    """An ssh or scp call that failed: no such host, refused keys, a scheduler's error."""


def clusters() -> dict[str, Cluster]:
    """The clusters louped.toml names; an entry missing a key or holding a bad one is an error
    naming it."""
    found: dict[str, Cluster] = {}
    for name, entry in (config().get("clusters") or {}).items():
        where = f"louped.toml: [clusters.{name}]"
        if not isinstance(entry, dict) or set(entry) != {"ssh", "provider", "dir"}:
            raise ValueError(f"{where} holds ssh, provider and dir")
        if not HOST.match(str(entry["ssh"])):
            raise ValueError(f"{where}: ssh is a Host from ~/.ssh/config, such as sol")
        if entry["provider"] not in get_args(Provider):
            raise ValueError(f"{where}: provider is one of {get_args(Provider)}")
        if not DIR.match(str(entry["dir"])):
            raise ValueError(f"{where}: dir is a folder path without spaces or quotes")
        found[name] = Cluster(name, entry["ssh"], entry["provider"], entry["dir"])
    return found


def get(name: str) -> Cluster:
    known = clusters()
    if name not in known:
        listed = ", ".join(known) or "none"
        raise ValueError(f"no cluster {name!r} in louped.toml (it names {listed}); add "
                         f'[clusters.{name}] with ssh, provider and dir')  # fmt: skip
    return known[name]


def _run(argv: list[str], what: str, timeout: int, stdin: str | None = None) -> str:
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise SshError(f"{argv[0]} is not installed on this machine") from exc
    except subprocess.TimeoutExpired as exc:
        raise SshError(f"{what} took longer than {timeout} s") from exc
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip() or "no output"
        raise SshError(f"{what} failed (exit {done.returncode}): {said}")
    return done.stdout


def ssh(host: str, command: str, timeout: int = SSH_TIMEOUT, stdin: str | None = None) -> str:
    """command run by the remote shell; its stdout."""
    return _run(["ssh", *OPTIONS, host, command], f"ssh {host} {command!r}", timeout, stdin)


def scp(source: str, target: str, timeout: int = COPY_TIMEOUT) -> None:
    _run(["scp", "-q", *OPTIONS, source, target], f"scp {source} {target}", timeout)


def start(cluster: Cluster, script: Path, job_id: str, after: str | None) -> tuple[str, str]:
    """Copy an exported job (louped-<id>.sh, or louped-<id>.tar.gz) into the cluster's dir and
    start it: sbatch, or nohup bash on a plain machine. after is a Slurm job id it waits for and
    needs to succeed. Returns the folder it was copied to and the scheduler's id (a process id
    for shell). Its output goes to <folder>/louped-<id>.out, its result under
    <folder>/louped-<id>/."""
    if after and cluster.provider == "shell":
        raise ValueError(f"{cluster.name} runs jobs with bash, which cannot wait for another; "
                         "--after needs a Slurm cluster")  # fmt: skip
    found = ssh(cluster.ssh, f"mkdir -p {cluster.dir} && cd {cluster.dir} && pwd").split()
    if not found:
        raise SshError(f"ssh {cluster.ssh}: pwd in {cluster.dir} printed nothing")
    folder = found[-1]
    scp(str(script), f"{cluster.ssh}:{folder}/{script.name}")
    job = f"louped-{job_id}"
    out = shlex.quote(f"{folder}/{job}.out")
    go = f"cd {shlex.quote(folder)} && "
    if script.name.endswith(".tar.gz"):  # a folder: job.sh works where it is unpacked
        go += f"tar -xzf {job}.tar.gz && rm {job}.tar.gz && cd {job} && "
        name = "job.sh"
    else:  # one file: it works in louped-<id>/ beside it
        name = script.name
    if cluster.provider == "shell":
        said = ssh(cluster.ssh, go + f"{{ nohup bash {name} > {out} 2>&1 < /dev/null & echo $!; }}")
    else:
        wait = f"--dependency=afterok:{after} --kill-on-invalid-dep=yes " if after else ""
        said = ssh(cluster.ssh, go + f"sbatch --parsable -o {out} {wait}{name}")
    lines = said.strip().splitlines()
    scheduler_id = lines[-1].split(";")[0].strip() if lines else ""
    if not scheduler_id.isdigit():
        raise SshError(f"starting {name} on {cluster.name} answered {said.strip()!r}, not a job id")
    return folder, scheduler_id


def states(cluster: Cluster, ids: list[str]) -> dict[str, str]:
    """Each job's state by its scheduler id: Slurm's (PENDING, RUNNING, COMPLETED, ...), or
    RUNNING and ENDED for a shell job. A job the scheduler does not list yet is left out."""
    ids = [i for i in ids if i.isdigit()]
    if not ids:
        return {}
    if cluster.provider == "shell":
        command = (f"for p in {' '.join(ids)}; do if kill -0 $p 2>/dev/null; then "
                   "echo $p'|RUNNING'; else echo $p'|ENDED'; fi; done")  # fmt: skip
    else:
        command = f"sacct -n -X -P -o JobID,State -j {','.join(ids)}"
    found: dict[str, str] = {}
    for line in ssh(cluster.ssh, command).splitlines():
        job, _, state = line.strip().partition("|")
        if job in ids and state:
            found[job] = state.split()[0].rstrip("+")  # "CANCELLED by 123"
    return found


def cancel(cluster: Cluster, scheduler_id: str) -> None:
    if not scheduler_id.isdigit():
        raise ValueError(f"{scheduler_id!r} is not a job id")
    if cluster.provider == "shell":
        ssh(cluster.ssh, f"pkill -TERM -P {scheduler_id}; kill {scheduler_id}")
    else:
        ssh(cluster.ssh, f"scancel {scheduler_id}")


def fetch(cluster: Cluster, path: str, target: Path) -> None:
    """Copy a file from the cluster to this machine; path is one louped made, with no spaces."""
    scp(f"{cluster.ssh}:{path}", str(target))


def tail(cluster: Cluster, path: str, lines: int = 80) -> str:
    return ssh(cluster.ssh, f"tail -n {lines} {shlex.quote(path)}")


#: Where huggingface_hub on the cluster reads a token, and where `hf auth login` writes one.
TOKEN = (
    'umask 077 && d="${HF_HOME:-$HOME/.cache/huggingface}" && mkdir -p "$d" && '
    'cat > "$d/token" && chmod 600 "$d/token" && echo "$d/token"'
)


def send_token(cluster: Cluster) -> str:
    """Copy this machine's Hugging Face token to the cluster, where gated models read it; on
    stdin, so it is in no command line or log. Returns where it went."""
    from huggingface_hub import get_token

    token = get_token()
    if token is None:
        raise ValueError(
            "no Hugging Face token on this machine: run hf auth login, or set HF_TOKEN"
        )
    return f"{cluster.ssh}:{ssh(cluster.ssh, TOKEN, stdin=token).strip()}"
