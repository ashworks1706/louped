"""Export a launch, run its job.sh as the other machine would, and import the result."""

import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from fastapi.testclient import TestClient

from loupe import stores
from loupe.server import create_app

SCRIPT = '''"""Writes one MLflow run and one eval, as an experiment would."""
from dataclasses import dataclass

import tyro
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import generate

from loupe.analysis import table
from loupe.tracking import log_json, start_run


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
    job = root.name.removeprefix("loupe-")
    assert name == f"loupe-{job}.tar.gz"
    script = (root / "job.sh").read_text()
    for line in ("#SBATCH -p public", "#SBATCH -q public", "#SBATCH -G a100:1",
                 "#SBATCH -t 2:00:00", "#SBATCH -C a100_80", "/scratch/$USER/huggingface",
                 'UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-300}"',
                 "python experiments/hello/run.py --name sol"):  # fmt: skip
        assert line in script
    assert (root / "experiments/hello/run.py").exists() and (root / "uv.lock").exists()
    [listed] = [j for j in api.get("/api/launch/jobs").json() if j["id"] == job]
    assert listed["status"] == "exported" and listed["title"].endswith("· sol")


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
    job = root.name.removeprefix("loupe-")
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
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LOUPE_", "INSPECT_"))}
    env |= {"PATH": f"{stub}:{env['PATH']}", "HOME": str(tmp_path)}
    env.pop("VIRTUAL_ENV", None)
    ran = subprocess.run(["bash", "job.sh"], cwd=root, env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    result = root / f"loupe-result-{job}.tar.gz"
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
