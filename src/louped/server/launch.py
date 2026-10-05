"""Launching from the UI: the commands louped already has, run as jobs one at a time.

Nothing here runs a model. A launchable is an existing command (an experiment script, `louped train`
or `louped grid` on a config, `louped sweep`, `louped new`, `inspect eval`), its form read from the
command's own argument parser;
a job is that command in a subprocess, its output in <home>/jobs/<id>/log.txt. What a job writes
lands in the stores like any run started from a shell, so the Runs page shows it while it runs.
Jobs run in the order they were launched, one at a time: one machine, usually one GPU.

Launching runs code on this machine, so the app only allows it on loopback (not with --expose),
and only for a JSON body, which a page on another origin cannot send without CORS allowing it.
Options are only read from, and jobs only started for, what the catalogue lists.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from louped.core import experiments_dir, home, logs_dir, trash

log = logging.getLogger(__name__)

#: exported: written out to run on another machine, waiting for its results to be imported.
Status = Literal["queued", "running", "succeeded", "failed", "cancelled", "exported"]


class Option(BaseModel):
    """One flag of a command, as its parser declares it."""

    flag: str
    kind: Literal["text", "bool", "list", "choice"]
    default: str | None
    help: str = ""
    choices: list[str] = []
    required: bool = False


class Launchable(BaseModel):
    id: str
    group: str
    title: str
    description: str = ""
    #: A config file's text to edit, for louped train and louped grid; else options only.
    config: str | None = None
    recipe: str | None = None


class LaunchRequest(BaseModel):
    id: str
    #: Flag to value, only the ones changed from the default.
    options: dict[str, str | bool | list[str]] = {}
    config: str | None = None
    recipe: str | None = None


class Job(BaseModel):
    id: str
    title: str
    argv: list[str]
    status: Status = "queued"
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started: datetime | None = None
    ended: datetime | None = None
    exit_code: int | None = None


class JobDetail(Job):
    log: str


RECIPES = ["sft", "dpo", "grpo", "classify", "reft"]
#: louped's own commands with a form: the command, its dataclass in louped.cli, what it does.
COMMANDS = {
    "new": ("New", "Start a research question: experiments/<name>/ with its README to fill in."),
    "sweep": ("Sweep", "A task under Steer at every layer and strength."),
    "features": (
        "Features",
        "Feature dashboards for an SAE over a dataset: density, histogram, "
        "top examples and the tokens each feature promotes.",
    ),
    "circuit": ("Circuit", "An attribution graph with circuit-tracer, shown on the Circuits page."),
    "bench": ("Bench", "Throughput under load and prefill by context, per weight format."),
    "endpoint-bench": (
        "EndpointBench",
        "Time to first token, latency and throughput of OpenAI-compatible servers by concurrency.",
    ),
    "judge": ("Judge", "Two eval runs judged pairwise by a local model: B's win rate over A."),
    "examples": (
        "Examples",
        "Example runs for every page from a tiny model trained here: "
        "vector, figures, grid, fine-tune, benchmark, circuit.",
    ),
}
#: The `louped data` steps a form can run; review is interactive and stays in a terminal.
DATA = {
    "export": "Read a system's logged model calls (trace files or Phoenix spans), redacted.",
    "collect": "Ask a teacher model each prompt: a training set when there are no logs.",
    "verify": "Drop malformed examples and duplicates.",
    "curate": "Build the training set from the examples a reviewer accepted.",
    "overlap": "Evaluation items that share an n-gram with the training set (contamination).",
    "stats": "What the training set holds and how much is still unreviewed.",
}
#: A new grid's config: edited on the page, run as a copy.
GRID = """# louped grid: every task under every condition and seed, each against the baseline
model: Qwen/Qwen2.5-0.5B-Instruct
tasks:
  main: experiments/my-question/task.py@my_task  # an Inspect task: file.py@name
conditions:
  base: {}
  steer: {interventions: {kind: steer, vector: my-vector, alpha: 4.0}}
metric: my_scorer/accuracy  # scorer/metric, as the Run page shows it
# held: other_scorer/accuracy  # a score that must not move
seeds: [0]
experiment: my-question
# extra: [latency/mean]  # more scores the tasks already have, each drawn against the metric
"""
TAIL = 64_000  # bytes of a job's log the UI shows


def _bin(name: str) -> str:
    """A console script installed beside this Python, so a job runs in the server's environment."""
    return str(Path(sys.executable).parent / name)


def _root() -> Path:
    return experiments_dir().parent


def catalogue() -> list[Launchable]:
    """Every experiment script with options, every training config, louped's commands, an eval."""
    out: list[Launchable] = []
    for script in sorted(experiments_dir().glob("*/*.py")):
        if 'if __name__ == "__main__":' in script.read_text(encoding="utf-8"):
            doc = re.match(r'\s*"""(.*?)(\n\n|""")', script.read_text(encoding="utf-8"), re.S)
            rel = script.relative_to(experiments_dir()).as_posix()
            out.append(Launchable(id=f"script:{rel}", group="Experiments", title=rel,
                                  description=doc[1].strip() if doc else ""))  # fmt: skip
    for cfg in sorted(experiments_dir().glob("*/*.yaml")):
        text = cfg.read_text(encoding="utf-8")
        if m := re.match(r"# louped train (\w+)", text):
            rel = cfg.relative_to(experiments_dir()).as_posix()
            out.append(Launchable(id=f"train:{rel}", group="Training", title=rel,
                                  description=f"louped train {m[1]}", config=text,
                                  recipe=m[1]))  # fmt: skip
    for cfg in sorted(experiments_dir().glob("*/*.yaml")):
        text = cfg.read_text(encoding="utf-8")
        if text.startswith("# louped grid"):
            rel = cfg.relative_to(experiments_dir()).as_posix()
            out.append(Launchable(id=f"grid:{rel}", group="Grids", title=rel,
                                  description="louped grid", config=text))  # fmt: skip
    for sub, what in DATA.items():
        out.append(Launchable(id=f"data:{sub}", group="Data", title=f"louped data {sub}",
                              description=what))  # fmt: skip
    for name, (_, what) in COMMANDS.items():
        out.append(Launchable(id=name, group="Commands", title=f"louped {name}", description=what))
    out.append(Launchable(id="grid", group="Commands", title="louped grid", config=GRID,
                          description="Conditions by tasks by seeds against a baseline, with "
                          "paired intervals and a moved/held verdict: one figure."))  # fmt: skip
    out.append(Launchable(id="eval", group="Commands", title="inspect eval",
                          description="Any Inspect task or inspect_evals benchmark, on any model; "
                          "louped/<model> takes interventions as model args."))  # fmt: skip
    return out


#: inspect eval's form: the flags a run is usually changed by, not all of Inspect's.
EVAL = [
    Option(flag="task", kind="text", default=None, required=True,
           help="inspect_evals/<name>, or file.py@task"),
    Option(flag="--model", kind="text", default="louped/Qwen/Qwen2.5-0.5B-Instruct",
           help="louped/<hub id or saved model>, or any Inspect model"),
    Option(flag="--limit", kind="text", default=None, help="Samples to run; all when empty."),
    Option(flag="--epochs", kind="text", default=None),
    Option(flag="--max-tokens", kind="text", default="512"),
    Option(flag="--temperature", kind="text", default=None),
    Option(flag="-M", kind="list", default=None,
           help="Model args as key=value, e.g. interventions={...} revision=<commit>"),
    Option(flag="-T", kind="list", default=None, help="Task args as key=value"),
]  # fmt: skip


#: louped train's options beside the config the page edits.
TRAIN = [
    Option(flag="--sweep", kind="list", default=None,
           help="key=value,value over the config, one per line or space: every combination "
                "trains as its own run, compared in one summary run. E.g. "
                "train.learning_rate=1e-4,2e-4 lora.r=8,16"),
    Option(flag="--dry-run", kind="bool", default="False",
           help="Print what would run, without loading a model."),
]  # fmt: skip


def options(launchable: str) -> list[Option]:
    """The command's options: read from its parser in a subprocess, since an experiment script's
    imports are heavy; the train recipes take a config and have none."""
    if launchable == "eval":
        return EVAL
    if launchable.startswith("train:"):
        return TRAIN
    if launchable == "grid" or launchable.startswith("grid:"):
        return []  # everything is in the config
    if launchable in COMMANDS:
        target = f"from louped.cli import {COMMANDS[launchable][0]} as Args"
    elif launchable.startswith("data:"):
        target = f"from louped.data.cli import {launchable.removeprefix('data:').title()} as Args"
    else:
        script = _script(launchable)
        target = ("import importlib.util, sys\n"
                  f"spec = importlib.util.spec_from_file_location('launched', {str(script)!r})\n"
                  "mod = sys.modules['launched'] = importlib.util.module_from_spec(spec)\n"
                  "spec.loader.exec_module(mod)\nArgs = getattr(mod, 'Args', None)")  # fmt: skip
    code = f"{target}\nfrom louped.server.launch import dump\ndump(Args)"
    done = subprocess.run([sys.executable, "-c", code], cwd=_root(), capture_output=True,
                          text=True, timeout=120)  # fmt: skip
    if done.returncode != 0:
        raise HTTPException(500, done.stderr.strip().splitlines()[-1] if done.stderr else "failed")
    return [Option.model_validate(o) for o in json.loads(done.stdout.splitlines()[-1])]


def dump(args: type | None) -> None:
    """Print a tyro dataclass's options as JSON, defaults from the dataclass; run by options in a
    subprocess."""
    import argparse
    import dataclasses

    import tyro

    if args is None:  # a script that takes no options
        print("[]")
        return
    defaults: dict[str, Any] = {}
    for f in dataclasses.fields(args):  # pyright: ignore[reportArgumentType]
        value = f.default_factory() if f.default_factory is not dataclasses.MISSING else f.default
        if value is not dataclasses.MISSING:
            defaults["--" + f.name.replace("_", "-")] = value
    out = []
    for a in tyro.extras.get_parser(args)._actions:
        flag = a.option_strings[0] if a.option_strings else a.dest
        if flag in ("-h", "--help"):
            continue
        boolean = isinstance(a, argparse.BooleanOptionalAction) or a.nargs == 0
        listed = a.nargs in ("*", "+")
        kind = "bool" if boolean else "choice" if a.choices else "list" if listed else "text"
        default = defaults.get(flag)
        default = " ".join(map(str, default)) if isinstance(default, list | tuple) else default
        help = re.sub(
            r"\s*\((default: .*?|required|fixed to: .*?)\)\s*$", "", a.help or "", flags=re.S
        )
        out.append({"flag": flag, "kind": kind, "help": help.strip(), "required": a.required,
                    "default": None if default is None else str(default),
                    "choices": [str(c) for c in a.choices or []]})  # fmt: skip
    print(json.dumps(out))


def _script(launchable: str) -> Path:
    script = (experiments_dir() / launchable.removeprefix("script:")).resolve()
    if experiments_dir().resolve() not in script.parents or script.suffix != ".py":
        raise HTTPException(400, f"not an experiment script: {launchable}")
    return script


def _grid_template(launchable: str) -> str:
    if launchable == "grid":
        return GRID
    config = (experiments_dir() / launchable.removeprefix("grid:")).resolve()
    if experiments_dir().resolve() not in config.parents:
        raise HTTPException(400, f"not a grid config: {launchable}")
    return config.read_text(encoding="utf-8")


def argv(req: LaunchRequest, job_dir: Path, remote: bool = False) -> list[str]:
    """The command line a request runs; values go in as separate arguments, never a shell. With
    remote, for an exported bundle: commands by name from its environment and paths relative to
    the bundle, whose root is job_dir's parent, with experiments/ beside job_dir."""
    flags: list[str] = []
    positional: list[str] = []
    for flag, value in req.options.items():
        if isinstance(value, bool):
            flags += [flag] if value else [flag.replace("--", "--no-", 1)]
        elif not flag.startswith("-"):
            positional += value if isinstance(value, list) else [value]
        elif isinstance(value, list):
            repeat = flag in ("-M", "-T")  # Inspect takes one key=value per flag
            flags += [x for v in value for x in (flag, v)] if repeat else [flag, *value]
        else:
            flags += [flag, value]
    exe = (lambda name: name) if remote else _bin

    def where(path: Path) -> str:
        """A path as the command sees it: in the bundle, relative to its root."""
        if not remote:
            return str(path)
        if path.is_relative_to(job_dir.parent):
            return path.relative_to(job_dir.parent).as_posix()
        return "experiments/" + path.relative_to(experiments_dir().resolve()).as_posix()

    if req.id == "eval":
        logs = [] if remote else ["--log-dir", str(logs_dir())]  # remote: INSPECT_LOG_DIR
        return [exe("inspect"), "eval", *positional, *flags, *logs]
    if req.id in COMMANDS:
        return [exe("louped"), req.id, *positional, *flags]
    if req.id.startswith("data:"):
        return [exe("louped"), "data", req.id.removeprefix("data:"), *positional, *flags]
    if req.id == "grid" or req.id.startswith("grid:"):
        config = job_dir / "grid.yaml"
        config.write_text(req.config or _grid_template(req.id), encoding="utf-8")
        return [exe("louped"), "grid", where(config)]
    if req.id.startswith("train:"):
        template = (experiments_dir() / req.id.removeprefix("train:")).resolve()
        if experiments_dir().resolve() not in template.parents:
            raise HTTPException(400, f"not a training config: {req.id}")
        if req.recipe not in RECIPES:
            raise HTTPException(400, f"recipe is one of {RECIPES}")
        config = job_dir / template.name
        config.write_text(req.config or template.read_text(encoding="utf-8"), encoding="utf-8")
        return [exe("louped"), "train", req.recipe, where(config), "--base-dir",
                where(template.parent), *flags]  # fmt: skip
    return [exe("python") if remote else sys.executable, where(_script(req.id)), *positional,
            *flags]  # fmt: skip


class Jobs:
    """The queue: jobs on disk under <home>/jobs, run one at a time by a worker thread. The worker
    holds a file lock on the folder, so two servers on one home still run one job at a time."""

    def __init__(self, work: bool = True) -> None:
        self.dir = home() / "jobs"
        self.env = {"LOUPED_HOME": str(home()), "INSPECT_LOG_DIR": str(logs_dir()),
                    "PYTHONUNBUFFERED": "1"}  # fmt: skip
        self.lock = threading.Condition()
        self.procs: dict[str, subprocess.Popen[bytes]] = {}
        self.cancelled: set[str] = set()
        if work:  # without, only records jobs: an import from the command line
            threading.Thread(target=self.work, daemon=True).start()

    def list(self) -> list[Job]:
        found = []
        for path in self.dir.glob("*/job.json"):
            try:
                found.append(Job.model_validate_json(path.read_text()))
            except ValueError:  # a job file from another version, or damaged: not ours to run
                continue
        return sorted(found, key=lambda j: j.created, reverse=True)

    def get(self, job_id: str) -> Job:
        path = self.dir / job_id / "job.json"
        if not re.fullmatch(r"[\w-]+", job_id) or not path.exists():
            raise HTTPException(404, f"no job {job_id}")
        return Job.model_validate_json(path.read_text())

    def save(self, job: Job) -> None:
        path = self.dir / job.id / "job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(job.model_dump_json())
        os.replace(tmp, path)  # a reader never sees half a file

    def record(self, job: Job) -> None:
        """Save a job the queue does not run: exported, or finished by an import."""
        (self.dir / job.id).mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.save(job)

    def submit(self, req: LaunchRequest, title: str) -> Job:
        job_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        job_dir = self.dir / job_id
        job_dir.mkdir(parents=True)
        job = Job(id=job_id, title=title, argv=argv(req, job_dir))
        with self.lock:
            self.save(job)
            self.lock.notify()
        return job

    def cancel(self, job_id: str) -> Job:
        with self.lock:
            job = self.get(job_id)
            if job.status == "queued":
                job = job.model_copy(update={"status": "cancelled", "ended": datetime.now(UTC)})
                self.save(job)
            elif job.status == "running" and (proc := self.procs.get(job_id)):
                self.cancelled.add(job_id)
                os.killpg(proc.pid, signal.SIGTERM)  # the worker records it when it exits
            return job

    def delete(self, job_id: str) -> None:
        """Move a job that has ended, with its output, to <home>/trash/jobs; its runs stay."""
        with self.lock:
            job = self.get(job_id)
            if job.status in ("queued", "running"):
                raise HTTPException(409, f"job {job_id} is {job.status}: cancel it first")
            trash(self.dir / job_id, "jobs")

    def work(self) -> None:
        import fcntl

        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / ".lock").open("w") as held:
            while True:  # another server on this home runs the queue until it stops
                try:
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    threading.Event().wait(5)
            for job in self.list():  # a server that stopped mid-job left it without a process
                if job.status == "running":
                    self.save(job.model_copy(update={"status": "failed", "ended": job.started}))
            while True:
                try:
                    self.step()
                except Exception:  # one bad job must not stop the queue
                    log.exception("launch worker")
                    threading.Event().wait(1)

    def step(self) -> None:
        """Run the oldest queued job to its end, or wait for one."""
        with self.lock:
            queued = [j for j in self.list() if j.status == "queued"]
            if not queued:
                self.lock.wait(timeout=5)
                return
            job = queued[-1].model_copy(update={"status": "running",
                                                "started": datetime.now(UTC)})  # fmt: skip
            self.save(job)
        code = -1
        try:
            with (self.dir / job.id / "log.txt").open("wb") as out:
                try:
                    proc = subprocess.Popen(job.argv, cwd=_root(), env=os.environ | self.env,
                                            stdout=out, stderr=subprocess.STDOUT,
                                            start_new_session=True)  # fmt: skip
                except OSError as exc:
                    out.write(f"could not start: {exc}\n".encode())
                else:
                    self.procs[job.id] = proc
                    code = proc.wait()
        finally:
            self.procs.pop(job.id, None)
            cancelled = job.id in self.cancelled
            self.cancelled.discard(job.id)
            status: Status = "cancelled" if cancelled else "succeeded" if code == 0 else "failed"
            with self.lock:
                self.save(job.model_copy(update={"status": status, "exit_code": code,
                                                 "ended": datetime.now(UTC)}))  # fmt: skip

    def detail(self, job_id: str) -> JobDetail:
        job = self.get(job_id)
        path = self.dir / job_id / "log.txt"
        text = path.read_bytes()[-TAIL:].decode(errors="replace") if path.exists() else ""
        return JobDetail(**job.model_dump(), log=text)


def require_json(request: Request) -> None:
    """Refuse a body that is not JSON: a page on another origin can only send JSON after a CORS
    preflight, which this server does not allow. For the routes that run code."""
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind != "application/json":
        raise HTTPException(415, "send JSON")


def router(enabled: bool) -> APIRouter:
    api = APIRouter(prefix="/api/launch")
    jobs = Jobs() if enabled else None

    def queue() -> Jobs:
        if jobs is None:
            raise HTTPException(403, "launching is off: this server was started with --expose")
        return jobs

    def known(launchable: str) -> Launchable:
        found = {x.id: x for x in catalogue()}
        if launchable not in found:
            raise HTTPException(400, f"unknown: {launchable}")
        return found[launchable]

    @api.get("")
    def launchables() -> list[Launchable]:
        queue()
        return catalogue()

    @api.get("/options")
    def launch_options(id: str) -> list[Option]:
        queue()
        known(id)  # only what the catalogue lists is imported
        try:
            return options(id)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504, f"reading {id}'s options took too long") from exc

    @api.post("", dependencies=[Depends(require_json)])
    def launch(req: LaunchRequest) -> Job:
        return queue().submit(req, known(req.id).title)

    @api.get("/jobs")
    def job_list() -> list[Job]:
        return queue().list()

    @api.get("/jobs/{job_id}")
    def job(job_id: str) -> JobDetail:
        return queue().detail(job_id)

    from louped.server import remote  # it builds on this module

    remote.routes(api, queue, known)

    @api.delete("/jobs/{job_id}", dependencies=[Depends(require_json)])
    def delete(job_id: str) -> None:
        queue().delete(job_id)

    @api.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_json)])
    def cancel(job_id: str) -> Job:
        return queue().cancel(job_id)

    return api
