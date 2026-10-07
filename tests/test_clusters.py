"""Submitting to a cluster over ssh, following the job there and bringing its result back, with
ssh, scp and the scheduler stood in for."""

import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from louped import clusters
from louped.server import create_app
from louped.server import remote as remote_module
from louped.server import submit as submit_module
from louped.server.launch import Jobs

TOML = """[clusters.sol]
ssh = "sol"
provider = "sol"
dir = "/scratch/$USER/louped"

[clusters.vm]
ssh = "me@box"
provider = "shell"
dir = "~/louped"
"""
GATED = """---
domain: honesty
status: active
gate:
  run: train.py
  require: [heldout/caving < 0.954]
  guards: [test.py]
chain: [train.py, gate, test.py]
---
"""
SCRIPT = 'if __name__ == "__main__":\n    print("ran")\n'


class Cluster:
    """ssh and scp as the cluster answers them: every call kept, sbatch numbering its jobs."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.scripts: dict[str, bytes] = {}
        self.states: dict[str, str] = {}
        self.results: dict[str, Path] = {}
        self.fail: dict[str, str] = {}
        self.next = 4100

    def __call__(self, argv: list[str], what: str, timeout: int, stdin: str | None = None) -> str:
        self.calls.append((argv, stdin))
        command = argv[-1]
        for word, said in self.fail.items():
            if word in " ".join(argv):
                raise clusters.SshError(f"{what} failed (exit 1): {said}")
        if argv[0] == "scp":
            source, target = argv[-2], argv[-1]
            if source.startswith("sol:"):  # bringing a result back
                name = source.rsplit("/", 1)[-1]
                if name not in self.results:
                    raise clusters.SshError(f"{what} failed (exit 1): No such file")
                shutil.copy(self.results[name], target)
            else:
                self.scripts[Path(source).name] = Path(source).read_bytes()
            return ""
        if command.endswith("&& pwd"):
            return "/scratch/ash/louped\n"
        if "sbatch" in command:
            self.next += 1
            return f"{self.next};sol\n"
        if "nohup" in command:
            return "777\n"
        if command.startswith("sacct"):
            return "".join(f"{i}|{s}\n" for i, s in self.states.items())
        if command.startswith("tail"):
            return "Traceback: CUDA out of memory\n"
        return ""

    def commands(self) -> list[str]:
        return [argv[-1] for argv, _ in self.calls if argv[0] == "ssh"]


@pytest.fixture
def cluster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Cluster:
    (tmp_path / "louped.toml").write_text(TOML)
    folder = tmp_path / "experiments" / "caving"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(GATED)
    for name in ("train.py", "test.py"):
        (folder / name).write_text(SCRIPT)
    monkeypatch.chdir(tmp_path)
    fake = Cluster()
    monkeypatch.setattr(clusters, "_run", fake)
    return fake


def job_sh(bundle: bytes) -> str:
    """The job.sh inside an exported louped-<id>.tar.gz."""
    with tarfile.open(fileobj=io.BytesIO(bundle)) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("/job.sh"))
        found = tar.extractfile(member)
        assert found is not None
        return found.read().decode()


def client() -> TestClient:
    return TestClient(create_app(launching=True), base_url="http://localhost")


def test_clusters_come_from_louped_toml_and_a_bad_entry_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "louped.toml").write_text(TOML)
    assert clusters.get("sol") == clusters.Cluster("sol", "sol", "sol", "/scratch/$USER/louped")
    with pytest.raises(ValueError, match=r"no cluster 'gpu' in louped.toml \(it names sol, vm\)"):
        clusters.get("gpu")
    for bad, said in (('ssh = "-oProxyCommand=x"', "a Host"), ('dir = "a; rm -rf ~"', "dir is"),
                      ('provider = "pbs"', "provider is one of")):  # fmt: skip
        key = bad.split(" ")[0]
        text = TOML.replace(next(x for x in TOML.splitlines() if x.startswith(key)), bad, 1)
        (tmp_path / "louped.toml").write_text(text)
        with pytest.raises(ValueError, match=said):
            clusters.clusters()


def test_ssh_runs_in_batch_mode_and_a_failure_carries_its_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 255, "", "ssh: Could not resolve hostname sol\n")

    monkeypatch.setattr(clusters.subprocess, "run", run)
    with pytest.raises(clusters.SshError, match=r"exit 255.*Could not resolve hostname sol"):
        clusters.ssh("sol", "true")
    assert seen[0][:5] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]

    def slow(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 60)

    monkeypatch.setattr(clusters.subprocess, "run", slow)
    with pytest.raises(clusters.SshError, match="took longer than 60 s"):
        clusters.ssh("sol", "sacct")


def test_sacct_and_shell_states_parse(cluster: Cluster) -> None:
    cluster.states = {"12": "RUNNING", "13": "CANCELLED by 501", "14": "PENDING"}
    sol = clusters.get("sol")
    assert clusters.states(sol, ["12", "13", "14", "15"]) == {
        "12": "RUNNING", "13": "CANCELLED", "14": "PENDING"}  # fmt: skip
    assert "sacct -n -X -P -o JobID,State -j 12,13,14,15" in cluster.commands()[-1]
    assert clusters.states(sol, ["x; rm"]) == {}  # ids only: nothing else reaches the shell


def test_submit_copies_the_job_there_starts_it_and_records_its_id(cluster: Cluster) -> None:
    api = client()
    body = {"id": "script:caving/train.py", "cluster": "sol", "target": {"gpu": "a100", "hours": 2}}
    got = api.post("/api/launch/submit", json=body)
    assert got.status_code == 200, got.text
    job = got.json()
    assert job["status"] == "submitted" and job["scheduler_id"] == "4101"
    assert job["cluster"] == "sol" and job["remote_dir"] == "/scratch/ash/louped"
    assert job["title"].endswith("· sol") and job["launch"] == "script:caving/train.py"
    mkdir, start = cluster.commands()
    assert mkdir == "mkdir -p /scratch/$USER/louped && cd /scratch/$USER/louped && pwd"
    assert "sbatch --parsable -o /scratch/ash/louped/louped-" in start
    assert "--dependency" not in start and start.endswith("job.sh")
    [data] = cluster.scripts.values()
    script = job_sh(data)
    assert "#SBATCH -G a100:1" in script and "LOUPED_LAUNCH=script:caving/train.py" in script
    assert "gated models will fail with 401" in script
    log = api.get(f"/api/launch/jobs/{job['id']}").json()["log"]
    assert "submitted to sol as job 4101" in log

    after = api.post("/api/launch/submit", json={**body, "after": job["id"]}).json()
    assert "--dependency=afterok:4101 --kill-on-invalid-dep=yes" in cluster.commands()[-1]
    assert after["after"] == job["id"]


def test_a_refused_submission_is_shown_on_its_job(cluster: Cluster) -> None:
    api = client()
    cluster.fail = {"sbatch": "sbatch: error: invalid partition specified: gpu"}
    body = {"id": "script:caving/train.py", "cluster": "sol", "target": {}}
    got = api.post("/api/launch/submit", json=body)
    assert got.status_code == 502 and "invalid partition specified" in got.text
    [job] = api.get("/api/launch/jobs").json()
    assert job["status"] == "failed"
    assert "invalid partition" in api.get(f"/api/launch/jobs/{job['id']}").json()["log"]
    unknown = api.post("/api/launch/submit", json={**body, "cluster": "nope"})
    assert unknown.status_code == 400 and "no cluster 'nope'" in unknown.text


def test_a_guarded_launch_is_refused_alone_but_runs_after_its_gate_step(
    cluster: Cluster, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = client()
    test = {"id": "script:caving/test.py", "cluster": "sol", "target": {}}
    refused = api.post("/api/launch/submit", json=test)
    assert refused.status_code == 409 and "no finished run yet" in refused.text
    gate = {"id": "gate", "cluster": "sol", "options": {"experiment": "caving"}, "target": {}}
    no_remote = api.post("/api/launch/submit", json=gate)
    assert no_remote.status_code == 400 and "set remote in louped.toml" in no_remote.text

    monkeypatch.setenv("LOUPED_REMOTE", "hf://buckets/ash/runs")
    monkeypatch.setattr(remote_module.sync, "is_local", lambda url: False)
    step = api.post("/api/launch/submit", json=gate).json()
    assert step["argv"] == ["louped", "gate", "caving", "--pull"]
    after = api.post("/api/launch/submit", json={**test, "after": step["id"]})
    assert after.status_code == 200, after.text
    assert f"afterok:{step['scheduler_id']}" in cluster.commands()[-1]


def test_a_chain_goes_in_order_each_step_after_the_last(
    cluster: Cluster, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOUPED_REMOTE", "hf://buckets/ash/runs")
    monkeypatch.setattr(remote_module.sync, "is_local", lambda url: False)
    titles = {"script:caving/train.py": "caving/train.py", "gate": "louped gate",
              "script:caving/test.py": "caving/test.py"}  # fmt: skip
    done = submit_module.chain("caving", "sol", Jobs(work=False), titles)
    assert [j.scheduler_id for j in done] == ["4101", "4102", "4103"]
    assert [j.after for j in done] == [None, done[0].id, done[1].id]
    starts = [c for c in cluster.commands() if "sbatch" in c]
    assert "--dependency" not in starts[0]
    assert "afterok:4101" in starts[1] and "afterok:4102" in starts[2]
    with pytest.raises(ValueError, match="cannot wait for another"):
        submit_module.chain("caving", "vm", Jobs(work=False), titles)


def result(tmp_path: Path, job: str, code: int) -> Path:
    """A louped-result-<id>.tar.gz as job.sh packs it, with no runs."""
    out = tmp_path / "far" / "out"
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps({
        "job": job, "host": "sol", "exit_code": code, "started": "2026-10-06T10:00:00Z",
        "ended": "2026-10-06T11:00:00+00:00", "home": str(out)}))  # fmt: skip
    (out / "log.txt").write_text("training… done\n")
    archive = tmp_path / f"louped-result-{job}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(out, arcname="out")
    return archive


def test_a_job_that_ends_brings_its_result_back_and_deletes_the_copy(
    cluster: Cluster, tmp_path: Path
) -> None:
    api = client()
    body = {"id": "script:caving/train.py", "cluster": "sol", "target": {}}
    job = api.post("/api/launch/submit", json=body).json()
    jobs = Jobs(work=False)
    cluster.states = {"4101": "RUNNING"}
    submit_module.follow(jobs)
    assert jobs.get(job["id"]).status == "running"
    cluster.states = {"4101": "COMPLETED"}
    cluster.results[f"louped-result-{job['id']}.tar.gz"] = result(tmp_path, job["id"], 0)
    submit_module.follow(jobs)
    done = jobs.get(job["id"])
    assert done.status == "succeeded" and done.exit_code == 0
    assert not list((jobs.dir / job["id"]).glob("*.tar.gz"))
    assert "training… done" in jobs.detail(job["id"]).log


def test_a_job_that_ends_with_no_result_shows_the_end_of_its_output(cluster: Cluster) -> None:
    api = client()
    body = {"id": "script:caving/train.py", "cluster": "sol", "target": {}}
    job = api.post("/api/launch/submit", json=body).json()
    jobs = Jobs(work=False)
    cluster.states = {"4101": "OUT_OF_MEMORY"}
    submit_module.follow(jobs)
    done = jobs.detail(job["id"])
    assert done.status == "failed"
    assert "sol says OUT_OF_MEMORY" in done.log and "CUDA out of memory" in done.log
    assert f"tail -n 80 /scratch/ash/louped/louped-{job['id']}.out" in cluster.commands()[-1]

    stop = api.post("/api/launch/submit", json=body).json()
    assert api.post(f"/api/launch/jobs/{stop['id']}/cancel", json={}).json()["status"] == (
        "cancelled"
    )
    assert cluster.commands()[-1] == "scancel 4102"


def test_a_shell_machine_runs_the_job_with_nohup(cluster: Cluster) -> None:
    api = client()
    body = {"id": "script:caving/train.py", "cluster": "vm", "target": {}}
    job = api.post("/api/launch/submit", json=body).json()
    assert job["scheduler_id"] == "777"
    start = cluster.commands()[-1]
    assert "{ nohup bash job.sh > /scratch/ash/louped/louped-" in start and "echo $!" in start
    refused = api.post("/api/launch/submit", json={**body, "after": job["id"]})
    assert refused.status_code == 400 and "--after needs a Slurm cluster" in refused.text


def test_the_token_goes_on_stdin_never_on_a_command_line(
    cluster: Cluster, monkeypatch: pytest.MonkeyPatch
) -> None:
    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "get_token", lambda: "hf_secret")
    original = cluster.__call__

    def answer(argv: list[str], what: str, timeout: int, stdin: str | None = None) -> str:
        original(argv, what, timeout, stdin)
        return "/home/ash/.cache/huggingface/token\n"

    monkeypatch.setattr(clusters, "_run", answer)
    where = clusters.send_token(clusters.get("sol"))
    assert where == "sol:/home/ash/.cache/huggingface/token"
    [(argv, stdin)] = cluster.calls
    assert stdin == "hf_secret" and "hf_secret" not in " ".join(argv)
    assert "umask 077" in argv[-1] and 'chmod 600 "$d/token"' in argv[-1]
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: None)
    with pytest.raises(ValueError, match="no Hugging Face token on this machine"):
        clusters.send_token(clusters.get("sol"))


def test_job_sh_warns_once_before_installing_when_there_is_no_token(cluster: Cluster) -> None:
    api = client()
    got = api.post("/api/launch/export", json={"id": "script:caving/train.py",
                                               "target": {"provider": "slurm"}})  # fmt: skip
    script = job_sh(got.content)
    assert script.index("hf_token=") < script.index("uv sync")
    check = script[script.index("hf_token=") : script.index("command -v uv")]

    def warned(env: dict[str, str]) -> bool:
        done = subprocess.run(["bash", "-c", check], env=env, capture_output=True, text=True)
        return "gated models will fail with 401" in done.stderr

    home = Path.cwd() / "home-dir"
    assert warned({"HOME": str(home)})
    assert not warned({"HOME": str(home), "HF_TOKEN": "x"})
    (home / ".cache/huggingface").mkdir(parents=True)
    (home / ".cache/huggingface/token").write_text("x")
    assert not warned({"HOME": str(home)})


def test_the_cli_submits_and_says_what_it_refuses(
    cluster: Cluster, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from louped import cli

    def run(*args: str) -> object:
        monkeypatch.setattr(sys, "argv", ["louped", *args])
        try:
            cli.main()
        except SystemExit as exc:
            return exc.code
        return 0

    assert run("submit", "script:caving/train.py", "--on", "sol", "--hours", "2") == 0
    assert "sol job 4101" in capsys.readouterr().out
    assert "#SBATCH -t 2:00:00" in job_sh(next(iter(cluster.scripts.values())))
    said = run("submit", "gate", "--on", "sol")
    assert isinstance(said, str) and "gate --experiment <name>" in said
    said = run("submit", "script:caving/test.py", "--on", "sol")
    assert isinstance(said, str) and "no finished run yet" in said
