"""Submitting an exported job to a cluster over ssh, and following it to its result.

Submit exports the launch as Export does, copies it into the cluster's dir and starts it (sbatch,
or nohup bash on a VM), and records the scheduler's id on the job. While the server runs, a
thread asks the cluster every FOLLOW seconds how its jobs are (sacct). A job that ends brings
its result back: pulled from the remote when the project has one the cluster reaches, else (or
when the job could not push) its louped-result-<id>.tar.gz copied here, imported and deleted. A
job that ends with no result says what the scheduler said and the end of its output.

--after makes a job wait on the cluster for an earlier one to succeed (afterok), so a chain runs
in order without this machine online. A gate step, `louped gate <experiment> --pull`, is a job of
its own that reads the earlier steps' runs from the remote; the launch it guards may follow it.
"""

from __future__ import annotations

import logging
import shutil
import tarfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from louped import clusters, sync
from louped.clusters import SshError
from louped.server.launch import LIVE, Job, Jobs, Launchable, require_json
from louped.server.remote import ExportRequest, Target, export, import_result, pull_results
from louped.stores import gates

log = logging.getLogger(__name__)

#: Seconds between asking the clusters how their jobs are.
FOLLOW = 60


class SubmitRequest(ExportRequest):
    #: A cluster named in louped.toml ([clusters.<name>]).
    cluster: str
    #: A louped job on the same cluster this one waits for and needs to succeed.
    after: str | None = Field(default=None, pattern=r"^[\w-]+$")


class ClusterInfo(BaseModel):
    name: str
    ssh: str
    provider: clusters.Provider
    dir: str


class SubmitFailed(RuntimeError):
    """Submitting failed after the job was recorded; the job says why, as its log."""


def _note(jobs: Jobs, job_id: str, text: str) -> None:
    """Add a line to a job's log, for what louped did with it; not again when it is the last."""
    path = jobs.dir / job_id / "log.txt"
    line = f"[louped] {text}\n"
    if path.exists() and path.read_text(encoding="utf-8", errors="replace").endswith(line):
        return
    with path.open("a", encoding="utf-8") as out:
        out.write(line)


def _needs_remote(cluster: str) -> None:
    """Refuse a gate step when the cluster cannot reach the project's remote: the step reads
    the earlier steps' runs from there."""
    remote = sync.configured()
    if remote is None or sync.is_local(remote):
        why = "has none" if remote is None else f"has {remote}, a folder on this machine"
        raise ValueError(f"a gate step on {cluster} reads the earlier steps' runs from the "
                         f"project's remote, and this project {why}: set remote in louped.toml "
                         "(Runs → Connect) so the steps push there")  # fmt: skip


def submit(req: SubmitRequest, jobs: Jobs, title: str) -> Job:
    """Export req, start it on its cluster, and record it as submitted. ValueError for a request
    that cannot go (an unknown cluster, a gate step with no remote); GateClosed and BadGate from
    its gate; SubmitFailed when ssh or the scheduler refused, the job saying why."""
    cluster = clusters.get(req.cluster)
    after = jobs.get(req.after) if req.after else None
    if after is not None and (after.cluster != cluster.name or not after.scheduler_id):
        raise ValueError(f"job {after.id} was not submitted to {cluster.name}")
    if after is not None and cluster.provider == "shell":
        raise ValueError(f"{cluster.name} runs jobs with bash, which cannot wait for another; "
                         "--after needs a Slurm cluster")  # fmt: skip
    # a launch right after its experiment's gate step is held by that step on the cluster
    chained = (
        after.argv[2] if after and after.launch == gates.GATE and len(after.argv) > 2 else None
    )
    gates.guard(req.id, chained)
    if req.id == gates.GATE:  # it pulls the steps' runs; louped gate needs evals and tracking
        _needs_remote(cluster.name)
        target = req.target
        if target.extras is None:
            target = target.model_copy(update={"extras": ["evals", "tracking"]})
        req = req.model_copy(update={"options": {**req.options, "--pull": True},
                                     "target": target})  # fmt: skip
    exported = req.model_copy(update={"target": req.target.model_copy(
        update={"provider": cluster.provider})})  # fmt: skip
    script, _, job = export(exported, jobs, title)
    job = job.model_copy(update={"title": f"{title} · {cluster.name}", "cluster": cluster.name,
                                 "after": after.id if after else None})  # fmt: skip
    jobs.record(job)
    try:
        folder, scheduler_id = clusters.start(cluster, script, job.id,
                                              after.scheduler_id if after else None)  # fmt: skip
    except (SshError, ValueError) as exc:
        _note(jobs, job.id, f"submitting to {cluster.name} failed: {exc}")
        jobs.record(job.model_copy(update={"status": "failed", "ended": datetime.now(UTC)}))
        raise SubmitFailed(f"submitting to {cluster.name} failed: {exc} (job {job.id})") from exc
    finally:
        shutil.rmtree(script.parent, ignore_errors=True)
    job = job.model_copy(update={"status": "submitted", "scheduler_id": scheduler_id,
                                 "remote_dir": folder})  # fmt: skip
    _note(jobs, job.id, f"submitted to {cluster.name} as job {scheduler_id}, in {folder}")
    jobs.record(job)
    return job


def chain(experiment: str, cluster: str, jobs: Jobs, titles: dict[str, str],
          target: Target | None = None) -> list[Job]:  # fmt: skip
    """Submit the steps the experiment's README lists under chain:, each waiting for the one
    before to succeed. Every step is checked before the first is sent. The gate step asks for no
    GPU."""
    steps = gates.chain(experiment)
    on = clusters.get(cluster)
    if on.provider == "shell" and len(steps) > 1:
        raise ValueError(f"{cluster} runs jobs with bash, which cannot wait for another; a chain "
                         "needs a Slurm cluster")  # fmt: skip
    base = target or Target()
    requests: list[SubmitRequest] = []
    for i, step in enumerate(steps):
        if step == gates.GATE:
            _needs_remote(cluster)
            req = SubmitRequest(id=step, cluster=cluster, options={"experiment": experiment},
                                target=base.model_copy(update={"gpus": 0, "hours": 1}))  # fmt: skip
        else:
            gate_before = experiment if gates.GATE in steps[:i] else None
            gates.guard(step, gate_before)
            req = SubmitRequest(id=step, cluster=cluster, target=base)
        if req.id not in titles:
            raise ValueError(f"{step} is not something louped can launch")
        requests.append(req)
    done: list[Job] = []
    for req in requests:
        req.after = done[-1].id if done else None
        done.append(submit(req, jobs, titles[req.id]))
    return done


def _ended(jobs: Jobs, job: Job, cluster: clusters.Cluster, state: str) -> None:
    """A job the scheduler says has ended: its result brought back, else what is known."""
    remote = sync.configured()
    if remote is not None and not sync.is_local(remote):
        try:
            pull_results(jobs)
        except (ValueError, OSError) as exc:  # unreachable now: try again on the next round
            _note(jobs, job.id, f"pulling its result from {remote} failed, retrying: {exc}")
            return
    if jobs.get(job.id).status not in LIVE:
        return
    name = f"louped-result-{job.id}.tar.gz"
    path = jobs.dir / job.id / name
    why = ""
    try:
        clusters.fetch(cluster, f"{job.remote_dir}/louped-{job.id}/{name}", path)
        import_result(path, jobs)
    except (SshError, ValueError, tarfile.TarError, KeyError) as exc:
        why = str(exc)
    finally:
        path.unlink(missing_ok=True)
    if jobs.get(job.id).status not in LIVE:
        return
    out = f"{job.remote_dir}/louped-{job.id}.out"
    try:
        end = clusters.tail(cluster, out)
    except SshError as exc:
        end = f"(could not read it: {exc})"
    _note(jobs, job.id, f"{cluster.name} says {state}, and no result came back ({why}). "
                        f"The end of {out}:\n{end}")  # fmt: skip
    status = "cancelled" if state == "CANCELLED" else "failed"
    jobs.record(job.model_copy(update={"status": status, "ended": datetime.now(UTC)}))


def follow(jobs: Jobs) -> None:
    """Ask each cluster how its live jobs are, once; record what changed."""
    live = [j for j in jobs.list() if j.cluster and j.scheduler_id and j.status in LIVE]
    for name in sorted({j.cluster for j in live if j.cluster}):
        mine = [j for j in live if j.cluster == name]
        try:
            cluster = clusters.get(name)
            found = clusters.states(cluster, [j.scheduler_id for j in mine if j.scheduler_id])
        except (ValueError, SshError) as exc:
            log.warning("following jobs on %s: %s", name, exc)
            continue
        for job in mine:
            state = found.get(job.scheduler_id or "")
            if state in clusters.RUNNING and job.status != "running":
                jobs.record(job.model_copy(update={"status": "running",
                                                   "started": datetime.now(UTC)}))  # fmt: skip
            elif state in clusters.ENDED:
                _ended(jobs, job, cluster, state)


def follower(jobs: Jobs) -> None:
    """Follow cluster jobs every FOLLOW seconds while the server runs."""

    def loop() -> None:
        while True:
            threading.Event().wait(FOLLOW)
            try:
                follow(jobs)
            except Exception:  # one bad round must not stop following
                log.exception("following cluster jobs")

    threading.Thread(target=loop, daemon=True).start()


def routes(api: APIRouter, queue: Callable[[], Jobs], known: Callable[[str], Launchable]) -> None:
    """The clusters, and submitting to one: off with --expose, like launching."""

    @api.get("/clusters")
    def cluster_list() -> list[ClusterInfo]:
        queue()
        try:
            return [ClusterInfo(name=c.name, ssh=c.ssh, provider=c.provider, dir=c.dir)
                    for c in clusters.clusters().values()]  # fmt: skip
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/submit", dependencies=[Depends(require_json)])
    def submit_job(req: SubmitRequest) -> Job:
        jobs, title = queue(), known(req.id).title
        try:
            return submit(req, jobs, title)
        except gates.GateClosed as exc:
            raise HTTPException(409, str(exc)) from exc
        except SubmitFailed as exc:
            raise HTTPException(502, str(exc)) from exc
        except ValueError as exc:  # BadGate too
            raise HTTPException(400, str(exc)) from exc
