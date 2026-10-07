"""Runs as bundles, kept in a remote: how a project's results move between machines and people.

A bundle is a folder laid out as a louped home: logs/ (Inspect's .eval files), mlflow.db with its
runs, artifacts/ beside it, and result.json saying where and when it ran. A job exported to a
cluster writes its out/ folder as one; `louped push` writes one from the runs this home made and
has not pushed; `louped import` and `louped pull` add one's runs to the local stores, skipping any
already there.

The remote is any fsspec URL: a folder (one in the repository keeps results with the code), an HF
Storage Bucket (hf://buckets/<user>/<name>), or S3-compatible storage such as Cloudflare R2
(s3://..., through s3fs, which Inspect brings). It is set as `remote` in
louped.toml, or LOUPED_REMOTE, which wins. Each push is a new folder under it and nothing is
rewritten, so two machines pushing never conflict. Model weights stay out of bundles: they are not
runs.

Bundles are written, pulled and unpacked under <home>/staging, on the stores' disk, never in the
system's temporary folder, and moved into the stores from there. A pulled artifact file bigger
than `large_artifact_mb` in louped.toml (LARGE_MB by default) stays in the remote: the run keeps a
pointer to it (mlflow_runs.REMOTE), lists it, and fetches it when it is opened.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import tomllib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from louped.core import home, logs_dir, require_space, tracking_uri
from louped.core.project import FILE, base, config, root
from louped.stores.mlflow_runs import REMOTE

#: What a bundle's result.json must hold for import; the rest is provenance.
RESULT = "result.json"
#: Pulled artifact files bigger than this many MB stay in the remote; louped.toml's
#: large_artifact_mb changes it.
LARGE_MB = 100


def large() -> int:
    """The size in bytes above which a pulled artifact file stays in the remote."""
    mb = config().get("large_artifact_mb", LARGE_MB)
    if isinstance(mb, bool) or not isinstance(mb, int | float) or mb < 0:
        raise ValueError(f"large_artifact_mb in louped.toml is a number of MB, not {mb!r}")
    return int(mb * 2**20)


@contextmanager
def staging() -> Iterator[Path]:
    """A new empty folder under <home>/staging, removed after: where bundles are unpacked, pulled
    and written, on the stores' own disk rather than in a small /tmp."""
    folder = home() / "staging" / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    folder.mkdir(parents=True)
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@dataclass
class Added:
    """What adding one bundle did."""

    result: dict[str, Any]
    runs: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def host(self) -> str:
        return str(self.result.get("host") or "remote")


def configured() -> str | None:
    """The remote this project names: LOUPED_REMOTE, else `remote` in louped.toml, a folder there
    taken from the project's root; None when neither is set. A louped.toml that does not parse is
    an error, not no remote."""
    if found := os.environ.get("LOUPED_REMOTE"):
        return found.rstrip("/")
    found = config().get("remote")
    if not found:
        return None
    found = str(found).rstrip("/")
    if "://" not in found and not Path(found).is_absolute():
        found = str((root() or Path.cwd()) / found)
    return found


def remote_url(url: str | None = None) -> str:
    """The remote: url, else the configured one."""
    found = url.rstrip("/") if url else configured()
    if not found:
        raise ValueError('no remote: set remote = "<url>" in louped.toml, or LOUPED_REMOTE')
    return found


def is_local(url: str) -> bool:
    """Whether the remote is a folder on this machine, which another machine cannot reach."""
    protocol = _fs(url)[0].protocol
    return bool({"file", "local"} & set(protocol if isinstance(protocol, tuple) else [protocol]))


#: An HF Storage Bucket remote: hf://buckets/<user>/<name>[/folder].
BUCKETS = "hf://buckets/"


class NeedsToken(ValueError):
    """An hf:// remote with no Hugging Face token on this machine."""


def bucket(url: str) -> str | None:
    """The bucket id (<user>/<name>) of an hf:// bucket remote; None for any other remote."""
    if not url.startswith(BUCKETS):
        return None
    parts = url[len(BUCKETS) :].split("/")
    if len(parts) < 2 or not all(parts[:2]):
        raise ValueError(f"{url}: an HF bucket remote is {BUCKETS}<user>/<name>")
    return "/".join(parts[:2])


def has_token() -> bool:
    from huggingface_hub import get_token

    return get_token() is not None


def save_token(token: str) -> str:
    """Check a Hugging Face token and keep it where huggingface_hub keeps it (`hf auth login`'s
    place), not in the project. Returns the account it belongs to."""
    from huggingface_hub import login, whoami

    try:
        user = str(whoami(token=token)["name"])
    except OSError as exc:  # HfHubHTTPError, a 401 for a bad token: say so
        raise ValueError(f"Hugging Face did not accept that token: {exc}") from exc
    login(token=token, skip_if_logged_in=False)
    return user


def suggested() -> str | None:
    """A remote for this project when none is set: a bucket of the signed-in account named after
    the project's folder. None without a token."""
    if not has_token():
        return None
    from huggingface_hub import whoami

    return f"{BUCKETS}{whoami()['name']}/{_slug(base().name).lower()}"


def set_remote(url: str) -> None:
    """Write `remote = "<url>"` into the project's louped.toml, replacing one that is there."""
    found = root()
    if found is None:
        raise ValueError("not in a louped project: run louped init first")
    path = found / FILE
    line = f"remote = {json.dumps(url.rstrip('/'))}"
    lines = path.read_text(encoding="utf-8").splitlines()
    at = next((i for i, x in enumerate(lines) if re.match(r"\s*remote\s*=", x)), None)
    if at is not None:
        lines[at] = line
    else:  # a top-level key goes before the first table
        first = next((i for i, x in enumerate(lines) if x.startswith("[")), len(lines))
        lines[first:first] = [line, ""] if first < len(lines) else ["", line]
    text = "\n".join(lines) + "\n"
    if tomllib.loads(text).get("remote") != url.rstrip("/"):
        raise ValueError(f"{path}: could not set remote there; add {line} by hand")
    path.write_text(text, encoding="utf-8")


def ready(url: str, create: bool) -> None:
    """Check what an hf:// remote needs before using it: a token, and with create, the bucket,
    made private if it does not exist."""
    found = bucket(url)
    if found is None:
        return
    if not has_token():
        raise NeedsToken(
            f"{url} needs a Hugging Face token with write access: run `hf auth login`, "
            "set HF_TOKEN, or paste one in the app"
        )
    if create:
        from huggingface_hub import create_bucket

        create_bucket(found, private=True, exist_ok=True)


def _fs(url: str) -> tuple[Any, str]:
    from fsspec.core import url_to_fs

    try:
        return url_to_fs(url)
    except ImportError as exc:  # e.g. s3:// without s3fs: name the package it wants
        raise ValueError(f"{url}: {exc}") from exc


def _state() -> dict[str, list[str]]:
    """What this home pushed (run ids) and pulled (bundle names)."""
    path = home() / "remote.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_state(state: dict[str, list[str]]) -> None:
    path = home() / "remote.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --- adding a bundle's runs to this home ---------------------------------------------------------


def add_bundle(
    out: Path, move: bool = False, left: dict[str, dict[str, Any]] | None = None
) -> Added:
    """Add the runs of a bundle folder to the local stores; runs already here are skipped. With
    move, its files are moved in, not copied: out is a staging copy. left names the artifact files
    that stayed in the remote ({bundle path: {"url", "size"}}), recorded on their runs."""
    result = json.loads((out / RESULT).read_text(encoding="utf-8"))
    added = Added(result)
    runs, skipped = _add_evals(out, added.host, move)
    # the node and GPUs it ran on, for the run page's provenance
    where = {f"louped.{k}": str(result[k]) for k in ("node", "gpu") if result.get(k)}
    more, again = _add_mlflow(out, added.host, str(result.get("home", "")), where, move,
                              left or {})  # fmt: skip
    added.runs, added.skipped = runs + more, skipped + again
    return added


def _add_evals(out: Path, host: str, move: bool) -> tuple[list[str], list[str]]:
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
        (shutil.move if move else shutil.copy2)(log, logs_dir() / log.name)
        added.append(run_id)
    _record_hosts(dict.fromkeys(added, host))
    return added, skipped


def _record_hosts(hosts: dict[str, str]) -> None:
    """Remember where added eval runs ran: Inspect logs carry no host of their own."""
    if not hosts:
        return
    path = home() / "hosts.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(known | hosts, indent=2, sort_keys=True), encoding="utf-8")


def _add_mlflow(
    out: Path, host: str, remote_home: str, where: dict[str, str], move: bool,
    left: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:  # fmt: skip
    db = out / "mlflow.db"
    if not db.exists():
        return [], []
    from mlflow import MlflowClient

    from louped.tracking.runs import experiment_id

    theirs = MlflowClient(tracking_uri=f"sqlite:///{db}")
    ours = MlflowClient(tracking_uri=tracking_uri())
    added: list[str] = []
    skipped: list[str] = []
    for experiment in theirs.search_experiments():
        for run in theirs.search_runs([experiment.experiment_id], max_results=10_000):
            # a run pushed from here and pulled back is ours already; one pulled before, too
            origin = run.data.tags.get("louped.imported_from") or run.info.run_id
            if (here := _local(ours, run.info.run_id, origin)) is not None:
                skipped.append(f"m-{here}")
                continue
            tags = {**run.data.tags, **where, "louped.host": host, "louped.imported_from": origin}
            local = _artifacts(out, run.info.artifact_uri or "", remote_home)
            at = f"{local.relative_to(out).as_posix()}/" if local is not None else None
            remote = {k[len(at) :]: v for k, v in left.items() if k.startswith(at)} if at else {}
            new = _copy_run(theirs, run, ours, experiment_id(experiment.name), tags, local, move,
                            remote)  # fmt: skip
            added.append(f"m-{new}")
    return added, skipped


def _local(client: Any, run_id: str, origin: str) -> str | None:
    """The local id of a bundle run already here: one this home made, or added before."""
    from mlflow.exceptions import MlflowException

    for mine in dict.fromkeys((run_id, origin)):
        try:
            return client.get_run(mine).info.run_id
        except MlflowException:
            pass
    found = client.search_runs(
        [e.experiment_id for e in client.search_experiments()],
        filter_string=f"tags.`louped.imported_from` = '{origin}'",
    )
    return found[0].info.run_id if found else None


def _copy_run(
    theirs: Any, run: Any, ours: Any, experiment: str, tags: dict[str, str], local: Path | None,
    move: bool = False, remote: dict[str, dict[str, Any]] | None = None,
) -> str:  # fmt: skip
    """One run copied between MLflow stores with its params, metric histories and artifacts: moved
    with move when both are folders here, and the files left in the remote recorded as pointers."""
    from mlflow.entities import Metric, Param
    from mlflow.utils.file_utils import local_file_uri_to_path

    new = ours.create_run(experiment, start_time=run.info.start_time, tags=tags,
                          run_name=run.info.run_name)  # fmt: skip
    params = [Param(k, v) for k, v in run.data.params.items()]
    for i in range(0, len(params), 100):  # MLflow's batch limits
        ours.log_batch(new.info.run_id, params=params[i : i + 100])
    metrics = [Metric(m.key, m.value, m.timestamp, m.step) for key in run.data.metrics
               for m in theirs.get_metric_history(run.info.run_id, key)]  # fmt: skip
    for i in range(0, len(metrics), 1000):
        ours.log_batch(new.info.run_id, metrics=metrics[i : i + 1000])
    uri = new.info.artifact_uri or ""
    if local is not None and local.is_dir() and move and uri.startswith("file:"):
        target = Path(local_file_uri_to_path(uri))
        target.mkdir(parents=True, exist_ok=True)
        for child in local.iterdir():
            shutil.move(child, target / child.name)
    elif local is not None and local.is_dir():
        ours.log_artifacts(new.info.run_id, str(local))
    if remote:
        ours.log_dict(new.info.run_id, remote, REMOTE)
    ours.set_terminated(new.info.run_id, run.info.status, end_time=run.info.end_time)
    return new.info.run_id


def _artifacts(out: Path, uri: str, remote_home: str) -> Path | None:
    """A bundle run's artifact folder inside out/: its path under the home that wrote it."""
    path = uri.removeprefix("file://")
    if remote_home and path.startswith(remote_home.rstrip("/") + "/"):
        return out / path[len(remote_home.rstrip("/")) + 1 :]
    return None


# --- writing a bundle of this home's runs --------------------------------------------------------


def write_bundle(dest: Path, result: dict[str, Any] | None = None) -> list[str]:
    """Write the finished runs this home made and has not pushed as a bundle at dest; returns
    their ids. Runs added from elsewhere stay out: they are some other home's to push."""
    dest.mkdir(parents=True)
    runs = _bundle_evals(dest) + _bundle_mlflow(dest)
    host = os.environ.get("LOUPED_HOST") or socket.gethostname()
    now = datetime.now(UTC).isoformat()
    meta = {"host": host, "node": socket.gethostname(), "exit_code": 0, "started": now,
            "ended": now} | (result or {})  # fmt: skip
    meta["home"] = str(dest)
    (dest / RESULT).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return runs


def _bundle_evals(dest: Path) -> list[str]:
    from louped.stores.evals import PREFIX, eval_logs, hosts

    pushed = set(_state().get("pushed", []))
    elsewhere = hosts()
    out: list[str] = []
    for path, log in eval_logs():
        run_id = PREFIX + log.eval.eval_id
        if log.status == "started" or run_id in pushed or run_id in elsewhere:
            continue
        (dest / "logs").mkdir(exist_ok=True)
        shutil.copy2(path, dest / "logs" / path.name)
        out.append(run_id)
    return out


def _bundle_mlflow(dest: Path) -> list[str]:
    if not Path(tracking_uri().removeprefix("sqlite:///")).exists():
        return []
    from mlflow import MlflowClient

    pushed = set(_state().get("pushed", []))
    ours = MlflowClient(tracking_uri=tracking_uri())
    theirs = MlflowClient(tracking_uri=f"sqlite:///{dest / 'mlflow.db'}")
    out: list[str] = []
    for experiment in ours.search_experiments():
        target: str | None = None
        for run in ours.search_runs([experiment.experiment_id], max_results=10_000):
            if (run.info.status not in ("FINISHED", "FAILED", "KILLED")
                    or f"m-{run.info.run_id}" in pushed
                    or "louped.imported_from" in run.data.tags):  # fmt: skip
                continue
            if target is None:
                location = (dest / "artifacts" / experiment.name).as_uri()
                target = theirs.create_experiment(experiment.name, artifact_location=location)
            uri = run.info.artifact_uri or ""
            local = Path(uri.removeprefix("file://")) if uri.startswith(("file:", "/")) else None
            # keep the run's id, so pulling it back here is recognised as ours
            tags = {**run.data.tags, "louped.imported_from": run.info.run_id}
            _copy_run(ours, run, theirs, target, tags, local)
            out.append(f"m-{run.info.run_id}")
    return out


# --- the remote ----------------------------------------------------------------------------------


@dataclass
class Pushed:
    remote: str
    bundle: str | None
    runs: list[str]


def push(url: str | None = None, result: Path | None = None) -> Pushed:
    """Push this home's new runs to the remote as one bundle. With result, a job's result.json,
    the bundle carries its job, host and exit code, and the job's log.txt beside it."""
    remote = remote_url(url)
    ready(remote, create=True)
    fs, top = _fs(remote)
    meta = json.loads(result.read_text(encoding="utf-8")) if result else None
    host = (meta or {}).get("host") or os.environ.get("LOUPED_HOST") or socket.gethostname()
    name = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{_slug(str(host))}-{secrets.token_hex(2)}"
    with staging() as tmp:
        bundle = tmp / name
        runs = write_bundle(bundle, meta)
        if not runs and meta is None:
            return Pushed(remote, None, [])
        if result is not None and (log := result.parent / "log.txt").exists():
            shutil.copy2(log, bundle / "log.txt")
        # result.json last: pull takes a folder holding it as a whole bundle
        files = sorted(p for p in bundle.rglob("*") if p.is_file() and p.name != RESULT)
        for path in [*files, bundle / RESULT]:
            target = f"{top}/{name}/{path.relative_to(bundle).as_posix()}"
            fs.makedirs(target.rsplit("/", 1)[0], exist_ok=True)
            fs.put_file(str(path), target)
    state = _state()
    state["pushed"] = sorted({*state.get("pushed", []), *runs})
    state["pulled"] = sorted({*state.get("pulled", []), name})  # its own bundle is no news here
    _save_state(state)
    return Pushed(remote, name, runs)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-." else "-" for c in text)[:40]


def pull(
    url: str | None = None, finish: Callable[[Added, Path], None] | None = None
) -> list[tuple[str, Added]]:
    """Add every bundle in the remote this home has not pulled. finish sees each bundle's folder
    before it is deleted (a job's log). Artifact files bigger than large() stay in the remote."""
    remote = remote_url(url)
    ready(remote, create=False)
    fs, top = _fs(remote)
    try:
        entries = sorted(fs.ls(top, detail=False))
    except FileNotFoundError as exc:
        raise ValueError(f"{remote} does not exist: nothing has been pushed there yet") from exc
    state = _state()
    seen = set(state.get("pulled", []))
    limit = large()
    out: list[tuple[str, Added]] = []
    for entry in entries:
        name = entry.rstrip("/").rsplit("/", 1)[-1]
        if name in seen or not fs.exists(f"{entry}/{RESULT}"):
            continue
        found: dict[str, dict[str, Any]] = fs.find(entry, detail=True)
        files = {path[len(entry.rstrip("/")) + 1 :]: info for path, info in found.items()}
        left = {rel: {"url": fs.unstrip_protocol(info["name"]), "size": int(info["size"])}
                for rel, info in files.items()
                if rel.startswith("artifacts/") and int(info.get("size") or 0) > limit}  # fmt: skip
        with staging() as tmp:
            local = tmp / name
            require_space(sum(int(i.get("size") or 0) for r, i in files.items() if r not in left),
                          tmp)  # fmt: skip
            for rel, info in files.items():
                if rel in left:
                    continue
                target = local / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                fs.get_file(info["name"], str(target))
            added = add_bundle(local, move=True, left=left)
            if finish is not None:
                finish(added, local)
        out.append((name, added))
        state["pulled"] = sorted({*state.get("pulled", []), name})
        _save_state(state)
    return out
