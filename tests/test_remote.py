"""Export a launch, run its job.sh as the other machine would, and import the result."""

import io
import json
import os
import socket
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from louped import stores
from louped.server import create_app
from louped.server import remote as remote_module

SCRIPT = '''"""Writes one MLflow run and one eval, as an experiment would."""
from dataclasses import dataclass

import tyro
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import generate

from louped.analysis import table
from louped.tracking import log_json, start_run


@dataclass
class Args:
    name: str = "x"


if __name__ == "__main__":
    args = tyro.cli(Args)
    with start_run("hello", name=f"far {args.name}") as run:
        log_json(table("t", ["a"], [[1]]), "views/00-t.json")
    out = [ModelOutput.from_content("mockllm/model", "yes")]
    data = [Sample(id=1, input="q", target="yes")]
    task = Task(dataset=data, solver=generate(), scorer=includes())
    eval(task, model=get_model("mockllm/model", custom_outputs=out), tags=["experiment:hello"],
         display="none")
    print("ran", args.name)
'''


def experiment(tmp_path: Path) -> None:
    folder = tmp_path / "experiments" / "hello"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("---\ndomain: inference\nstatus: active\n---\n# hello\n")
    (folder / "run.py").write_text(SCRIPT)


def client() -> TestClient:
    return TestClient(create_app(launching=True), base_url="http://localhost")


def export(api: TestClient, target: dict) -> tuple[str, bytes]:
    body = {"id": "script:hello/run.py", "options": {"--name": "sol"}, "target": target}
    got = api.post("/api/launch/export", json=body)
    assert got.status_code == 200, got.text
    name = got.headers["content-disposition"].split("filename=")[1].strip('"')
    return name, got.content


def unpack(data: bytes, where: Path) -> Path:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(where, filter="data")
    [root] = list(where.iterdir())
    return root


def test_a_sol_bundle_asks_sol_for_its_gpu_and_runs_the_launch_command(tmp_path: Path) -> None:
    experiment(tmp_path)
    api = client()
    name, data = export(api, {"provider": "sol", "gpu": "a100", "gpus": 1, "hours": 2,
                              "constraint": "a100_80"})  # fmt: skip
    root = unpack(data, tmp_path / "far")
    job = root.name.removeprefix("louped-")
    assert name == f"louped-{job}.tar.gz"
    script = (root / "job.sh").read_text()
    for line in ("#SBATCH -p public", "#SBATCH -q public", "#SBATCH -G a100:1",
                 "#SBATCH -t 2:00:00", "#SBATCH -C a100_80", "/scratch/$USER/huggingface",
                 'UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-300}"',
                 "python experiments/hello/run.py --name sol"):  # fmt: skip
        assert line in script
    assert (root / "experiments/hello/run.py").exists() and (root / "uv.lock").exists()
    [listed] = [j for j in api.get("/api/launch/jobs").json() if j["id"] == job]
    assert listed["status"] == "exported" and listed["title"].endswith("· sol")


def test_a_job_installs_the_extras_its_experiment_declares(tmp_path: Path) -> None:
    experiment(tmp_path)
    api = client()
    _, data = export(api, {"provider": "sol"})
    script = (unpack(data, tmp_path / "a") / "job.sh").read_text()
    assert "--extra interp --extra evals --extra tracking --extra train" in script  # defaults
    readme = tmp_path / "experiments" / "hello" / "README.md"
    readme.write_text("---\ndomain: inference\nstatus: active\nextras: tracking\n---\n# hello\n")
    _, data = export(api, {"provider": "sol"})
    root = unpack(data, tmp_path / "b")
    assert "uv sync --locked --no-dev --extra tracking\n" in (root / "job.sh").read_text()
    assert json.loads((root / "louped.json").read_text())["target"]["extras"] == ["tracking"]
    _, data = export(api, {"provider": "sol", "extras": ["interp", "tracking"]})  # the form wins
    assert (
        "--extra interp --extra tracking\n" in (unpack(data, tmp_path / "c") / "job.sh").read_text()
    )
    readme.write_text("---\ndomain: inference\nstatus: active\nextras: gpu-magic\n---\n")
    bad = api.post("/api/launch/export", json={"id": "script:hello/run.py", "options": {},
                                               "target": {"provider": "sol"}})  # fmt: skip
    assert bad.status_code == 400 and "unknown extras ['gpu-magic']" in bad.text


def test_a_bad_sol_gpu_and_an_unsafe_field_are_refused(tmp_path: Path) -> None:
    experiment(tmp_path)
    api = client()
    body = {"id": "script:hello/run.py", "options": {}}
    bad = api.post("/api/launch/export", json={**body, "target": {"gpu": "v100"}})
    assert bad.status_code == 400 and "Sol's GPUs" in bad.text
    unsafe = api.post("/api/launch/export", json={**body, "target": {"qos": "x; rm -rf ~"}})
    assert unsafe.status_code == 422


def test_a_result_run_elsewhere_imports_as_if_it_ran_here(tmp_path: Path) -> None:
    experiment(tmp_path)
    api = client()
    _, data = export(api, {"provider": "shell"})
    root = unpack(data, tmp_path / "far")
    job = root.name.removeprefix("louped-")
    assert "#SBATCH" not in (root / "job.sh").read_text()
    (root / "out/vendor/harness").mkdir(parents=True)  # a paper harness's venv stays behind
    (root / "out/vendor/harness/big").write_text("x")
    # The other machine: uv is there and the environment is this one.
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text("#!/bin/sh\nexit 0\n")
    (stub / "uv").chmod(0o755)
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/activate").write_text(f'export PATH="{Path(sys.executable).parent}:$PATH"\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LOUPED_", "INSPECT_"))}
    env |= {"PATH": f"{stub}:{env['PATH']}", "HOME": str(tmp_path)}
    env.pop("VIRTUAL_ENV", None)
    ran = subprocess.run(["bash", "job.sh"], cwd=root, env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    result = root / f"louped-result-{job}.tar.gz"
    with tarfile.open(result) as tar:
        assert not [n for n in tar.getnames() if n.startswith("out/vendor")]

    got = api.post("/api/launch/import", content=result.read_bytes(),
                   headers={"content-type": "application/gzip"})  # fmt: skip
    assert got.status_code == 200, got.text
    done = got.json()
    assert done["job"] == job and done["host"] == "vm" and done["exit_code"] == 0
    runs = {r.id: r for r in stores.list_runs()}
    assert set(done["runs"]) <= set(runs) and len(done["runs"]) == 2
    analysis = next(runs[r] for r in done["runs"] if r.startswith("m-"))
    evaled = next(runs[r] for r in done["runs"] if r.startswith("e-"))
    assert analysis.name == "far sol" and analysis.experiment == "hello"
    assert evaled.experiment == "hello" and evaled.model == "mockllm/model"
    assert {analysis.host, evaled.host} == {"vm"}
    assert stores.get_run(analysis.id).tags["louped.node"] == socket.gethostname()
    assert [v.view.title for v in stores.list_views(analysis.id)] == ["t"]
    detail = api.get(f"/api/launch/jobs/{job}").json()
    assert detail["status"] == "succeeded" and "ran sol" in detail["log"]

    again = api.post("/api/launch/import-path", json={"path": str(result)}).json()
    assert again["runs"] == [] and sorted(again["skipped"]) == sorted(done["runs"])


def test_import_refuses_what_is_not_a_result_and_an_exposed_server(tmp_path: Path) -> None:
    api = client()
    junk = io.BytesIO()
    with tarfile.open(fileobj=junk, mode="w:gz") as tar:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    got = api.post("/api/launch/import", content=junk.getvalue(),
                   headers={"content-type": "application/gzip"})  # fmt: skip
    assert got.status_code == 400 and not (tmp_path.parent / "escape.txt").exists()
    assert api.post("/api/launch/import", content=b"{}",
                    headers={"content-type": "application/json"}).status_code == 415  # fmt: skip
    exposed = TestClient(create_app(), base_url="http://localhost")
    refused = exposed.post("/api/launch/import-path", json={"path": str(tmp_path)})
    assert refused.status_code == 403


def git(where: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(where), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)  # fmt: skip


def test_a_pushed_project_exports_as_one_file_whose_job_pushes_its_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    monkeypatch.setenv("LOUPED_EXPERIMENTS", str(project / "experiments"))
    experiment(project)
    remote = tmp_path / "runs"
    (project / "louped.toml").write_text(f'remote = "{remote}"\n')
    (project / ".gitignore").write_text(".louped/\n")
    git(tmp_path, "init", "-q", "--bare", "origin.git")
    git(project, "init", "-q", "-b", "main")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "x")
    monkeypatch.chdir(project)
    monkeypatch.setattr(remote_module, "_checkout", lambda: None)  # louped as a release
    api = client()
    body = {"id": "script:hello/run.py", "options": {"--name": "sol"},
            "target": {"provider": "shell"}}  # fmt: skip
    # a folder here is no remote for the cluster: the job packs its result and the note says why
    got = api.post("/api/launch/export", json=body)
    assert "cannot reach" in got.headers["x-louped-note"]
    # the "cluster" in this test is this machine, so its folder stands in for a bucket
    monkeypatch.setattr(remote_module.sync, "is_local", lambda url: False)

    got = api.post("/api/launch/export", json={"id": "script:hello/run.py",
                                               "options": {"--name": "sol"},
                                               "target": {"provider": "shell"}})  # fmt: skip
    assert got.status_code == 200 and "not pushed" in got.headers["x-louped-note"]
    git(project, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(project, "push", "-q", "origin", "main")
    (project / "experiments/hello/notes.txt").write_text("draft")
    got = api.post("/api/launch/export", json={"id": "script:hello/run.py",
                                               "options": {"--name": "sol"},
                                               "target": {"provider": "shell"}})  # fmt: skip
    assert "notes.txt is not committed" in got.headers["x-louped-note"]
    (project / "experiments/hello/notes.txt").unlink()

    name, data = export(api, {"provider": "shell"})
    assert name.endswith(".sh")
    job = name.removeprefix("louped-").removesuffix(".sh")
    script = data.decode()
    assert "git clone --quiet" in script and "louped push --result out/result.json" in script
    assert "sync]==" in script  # the job installs what pushing needs

    far = tmp_path / "far"
    (far / f"louped-{job}/.venv/bin").mkdir(parents=True)
    (far / name).write_bytes(data)
    activate = f'export PATH="{Path(sys.executable).parent}:$PATH"\n'
    (far / f"louped-{job}/.venv/bin/activate").write_text(activate)
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text("#!/bin/sh\nexit 0\n")
    (stub / "uv").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LOUPED_", "INSPECT_"))}
    env |= {"PATH": f"{stub}:{env['PATH']}", "HOME": str(tmp_path)}
    env.pop("VIRTUAL_ENV", None)
    env.pop("MLFLOW_TRACKING_URI", None)
    ran = subprocess.run(["bash", name], cwd=far, env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "Results pushed to" in ran.stdout
    assert not list((far / f"louped-{job}").glob("*.tar.gz"))

    pulled = api.post("/api/launch/pull", json={})
    assert pulled.status_code == 200, pulled.text
    [done] = pulled.json()
    assert done["job"] == job and done["host"] == "vm" and len(done["runs"]) == 2
    detail = api.get(f"/api/launch/jobs/{job}").json()
    assert detail["status"] == "succeeded" and "ran sol" in detail["log"]
    assert api.post("/api/launch/pull", json={}).json() == []


def test_a_git_url_with_credentials_never_goes_into_job_sh(tmp_path: Path) -> None:
    project = tmp_path / "project"
    experiment(project)
    git(tmp_path, "init", "-q", "--bare", "origin.git")
    git(project, "init", "-q", "-b", "main")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "x")
    git(project, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(project, "push", "-q", "origin", "main")
    assert isinstance(remote_module._clone([project / "experiments"]), remote_module.Clone)
    git(project, "remote", "set-url", "origin", "https://me:ghp_secret@github.com/me/p.git")
    assert "credentials" in str(remote_module._clone([project / "experiments"]))
    (project / "experiments/hello/a b.txt").write_text("x")
    git(project, "mv", "experiments/hello/run.py", "experiments/hello/main.py")
    assert str(remote_module._clone([project / "experiments"])).startswith(
        "experiments/hello/main.py is not committed (and 1 more)"
    )
