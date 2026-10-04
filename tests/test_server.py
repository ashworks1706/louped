import json
from pathlib import Path

from fastapi.testclient import TestClient

from louped.server import create_app


def test_health() -> None:
    body = TestClient(create_app(), base_url="http://localhost").get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["launching"] is False
    launching = TestClient(create_app(launching=True), base_url="http://localhost")
    assert launching.get("/api/health").json()["launching"] is True


def test_serves_the_ui_export(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>louped</html>")
    client = TestClient(create_app(tmp_path), base_url="http://localhost")
    assert "louped" in client.get("/").text
    assert client.get("/api/health").status_code == 200


def test_missing_ui_dir_serves_api_only(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "absent"), base_url="http://localhost")
    assert client.get("/").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_playground_without_a_model_says_so() -> None:
    client = TestClient(create_app(), base_url="http://localhost")
    info = client.get("/api/playground").json()
    assert info == {"model": None, "layers": None, "heads": None, "bank": [], "diffusion": False,
                    "switchable": False}  # fmt: skip
    assert client.post("/api/playground/generate", json={"prompt": "hi"}).status_code == 409
    assert client.post("/api/playground/inspect", json={"prompt": "hi"}).status_code == 409
    assert client.post("/api/playground/load", json={"model": "x"}).status_code == 403  # exposed


def test_inspect_view_is_served_read_only_over_the_eval_logs() -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample

    from louped import stores
    from louped.core import logs_dir

    eval(Task(dataset=[Sample(input="hi", target="hi")]), model="mockllm/model",
         log_dir=str(logs_dir()), display="none")  # fmt: skip
    client = TestClient(create_app(), base_url="http://localhost")
    (run,) = stores.list_runs()
    log = client.get(f"/api/runs/{run.id}").json()["log"]
    assert (logs_dir() / log).is_file()
    assert "Inspect View" in client.get("/inspect/").text
    files = client.get("/api/log-files").json()["files"]
    assert [f["name"].endswith(log) for f in files] == [True]
    name = files[0]["name"]
    assert client.get(f"/api/logs/{name}").status_code == 200
    assert client.get("/api/logs/file:///etc/passwd").status_code == 403
    before = (logs_dir() / log).read_bytes()
    viewer = {"X-Inspect-View-Request": "true"}  # what Inspect's own app sends on a write
    assert client.delete(f"/api/log-delete/{name}", headers=viewer).status_code == 403
    edit = {"edits": [{"type": "tags", "tags_add": ["x"]}], "provenance": {"author": "x"}}
    assert client.post(f"/api/log-edit/{name}", json=edit, headers=viewer).status_code == 403
    assert (logs_dir() / log).read_bytes() == before
    assert client.get("/api/health").status_code == 200


def test_circuit_graphs_are_listed_and_served_to_their_viewer() -> None:
    import json

    from louped.core import graphs_dir, home

    client = TestClient(create_app(), base_url="http://localhost")
    assert client.get("/api/graphs").json() == []
    assert client.get("/circuit/").status_code == 404
    root = graphs_dir()
    (root / "viewer" / "index.html").write_text("<title>Attribution Graphs</title>")
    meta = {"graphs": [{"slug": "capital", "prompt": "The capital of France is", "scan": "s"}]}
    (root / "graph-metadata.json").write_text(json.dumps(meta))
    (root / "capital.json").write_text('{"nodes": [], "links": []}')
    (home() / "secret.json").write_text('"secret"')
    assert [g["slug"] for g in client.get("/api/graphs").json()] == ["capital"]
    assert "Attribution Graphs" in client.get("/circuit/").text
    assert client.get("/circuit/data/graph-metadata.json").json() == meta
    assert client.get("/circuit/graph_data/capital.json").json()["nodes"] == []
    for path in ["/circuit/graph_data/..%2Fsecret.json", "/circuit/data/../secret.json",
                 "/circuit/graph_data/%2e%2e/secret.json"]:  # fmt: skip
        assert "secret" not in client.get(path).text


def test_only_this_machine_is_answered() -> None:
    assert TestClient(create_app()).get("/api/health").status_code == 400
    assert TestClient(create_app(), base_url="http://127.0.0.1").get("/api/health").is_success


def test_the_ui_launches_an_experiment_as_a_job_and_reads_its_log(tmp_path) -> None:
    import time

    exp = tmp_path / "experiments" / "hello"
    exp.mkdir(parents=True)
    (exp / "run.py").write_text(
        '"""Say hello."""\n'
        "from dataclasses import dataclass\n\nimport tyro\n\n\n@dataclass\nclass Args:\n"
        '    name: str = "world"\n    """Who to greet."""\n    loud: bool = False\n'
        "    times: tuple[int, ...] = (1,)\n\n\n"
        'if __name__ == "__main__":\n    a = tyro.cli(Args)\n'
        "    print(('HELLO' if a.loud else 'hello'), a.name, sum(a.times))\n"
    )
    (exp / "sft.yaml").write_text("# louped train sft experiments/hello/sft.yaml\nname: x\n")
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    ids = {x["id"]: x for x in client.get("/api/launch").json()}
    assert ids["script:hello/run.py"]["description"] == "Say hello."
    assert ids["train:hello/sft.yaml"]["recipe"] == "sft" and {"eval", "sweep"} <= set(ids)
    assert {"data:export", "data:curate"} <= set(ids) and "data:review" not in ids  # interactive
    assert {"features", "circuit", "sweep", "new", "grid"} <= set(ids)
    assert ids["grid"]["config"].startswith("# louped grid") and ids["grid"]["recipe"] is None
    assert client.get("/api/launch/options?id=grid").json() == []
    new = {o["flag"]: o for o in client.get("/api/launch/options?id=new").json()}
    assert new["name"]["required"] and "louped.toml" in new["--domain"]["help"]
    train = {o["flag"] for o in client.get("/api/launch/options?id=train:hello/sft.yaml").json()}
    assert train == {"--sweep", "--dry-run"}
    export = {o["flag"]: o for o in client.get("/api/launch/options?id=data:export").json()}
    assert export["--source"]["choices"] == ["traces", "phoenix"] and export["--name"]["required"]
    opts = {o["flag"]: o for o in client.get("/api/launch/options?id=script:hello/run.py").json()}
    assert opts["--name"] == {"flag": "--name", "kind": "text", "default": "world",
                              "help": "Who to greet.", "choices": [],
                              "required": False}  # fmt: skip
    assert opts["--loud"]["kind"] == "bool" and opts["--times"]["kind"] == "list"

    body = {"id": "script:hello/run.py", "options": {"--name": "louped", "--loud": True,
                                                    "--times": ["2", "3"]}}  # fmt: skip
    job = client.post("/api/launch", json=body).json()
    detail: dict = {}
    for _ in range(200):
        detail = client.get(f"/api/launch/jobs/{job['id']}").json()
        if detail["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert detail["status"] == "succeeded" and detail["log"].strip() == "HELLO louped 5"
    assert client.post("/api/launch", content=json.dumps(body)).status_code == 415  # not JSON
    assert client.post(f"/api/launch/jobs/{job['id']}/cancel").status_code == 415
    assert client.post("/api/launch", json={"id": "script:../x.py"}).status_code == 400
    off = TestClient(create_app(), base_url="http://localhost")
    assert off.post("/api/launch", json=body).status_code == 403


def test_launch_builds_train_and_eval_command_lines(tmp_path) -> None:
    from louped.core import experiments_dir, logs_dir
    from louped.server.launch import LaunchRequest, argv

    exp = experiments_dir() / "rl"
    exp.mkdir(parents=True)
    (exp / "grpo.yaml").write_text("# louped train grpo\nname: a\n")
    line = argv(LaunchRequest(id="train:rl/grpo.yaml", recipe="grpo", config="name: b\n"), tmp_path)
    assert line[1:4] == ["train", "grpo", str(tmp_path / "grpo.yaml")]
    assert (
        line[4:] == ["--base-dir", str(exp)] and (tmp_path / "grpo.yaml").read_text() == "name: b\n"
    )
    swept = argv(LaunchRequest(id="train:rl/grpo.yaml", recipe="grpo",
                               options={"--sweep": ["lora.r=4,8"]}), tmp_path)  # fmt: skip
    assert swept[-2:] == ["--sweep", "lora.r=4,8"]
    options = {"task": "inspect_evals/gsm8k", "--limit": "5",
               "-M": ["interventions={\"kind\": \"steer\"}", "revision=abc"]}  # fmt: skip
    line = argv(LaunchRequest(id="eval", options=options), tmp_path)
    assert line[1:] == ["eval", "inspect_evals/gsm8k", "--limit", "5",
                        "-M", 'interventions={"kind": "steer"}', "-M", "revision=abc",
                        "--log-dir", str(logs_dir())]  # fmt: skip


def test_launch_runs_a_grid_config_as_a_copy_and_scaffolds_an_experiment(tmp_path) -> None:
    import pytest

    from louped import stores
    from louped.core import experiments_dir
    from louped.server.launch import GRID, LaunchRequest, argv, catalogue
    from louped.stores.experiments import BadExperiment, scaffold

    exp = experiments_dir() / "kernels"
    exp.mkdir(parents=True)
    (exp / "README.md").write_text("---\ndomain: inference\nstatus: parked\n---\n# kernels\n")
    (exp / "grid.yaml").write_text("# louped grid\nmodel: a\n")
    line = argv(LaunchRequest(id="grid:kernels/grid.yaml"), tmp_path)
    assert line[1:] == ["grid", str(tmp_path / "grid.yaml")]
    assert (tmp_path / "grid.yaml").read_text() == "# louped grid\nmodel: a\n"
    argv(LaunchRequest(id="grid", config="model: b\n"), tmp_path)
    assert (tmp_path / "grid.yaml").read_text() == "model: b\n"
    argv(LaunchRequest(id="grid"), tmp_path)
    assert (tmp_path / "grid.yaml").read_text() == GRID
    new = argv(LaunchRequest(id="new", options={"name": "my-q", "--domain": "honesty"}), tmp_path)
    assert new[1:] == ["new", "my-q", "--domain", "honesty"]

    scaffold("my-q", "honesty")
    found = {e.name: e for e in stores.list_experiments()}["my-q"]
    assert found.domain == "honesty" and found.status == "active"
    assert "script:my-q/run.py" in {x.id for x in catalogue()}
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    opts = {o["flag"] for o in client.get("/api/launch/options?id=script:my-q/run.py").json()}
    assert opts == {"--model", "--seed"}
    for name, domain in (("my-q", "honesty"), ("My Q", "honesty"), ("other", "nope")):
        with pytest.raises(BadExperiment):
            scaffold(name, domain)


def test_a_running_job_is_stopped_from_the_ui(tmp_path) -> None:
    import time

    exp = tmp_path / "experiments" / "slow"
    exp.mkdir(parents=True)
    (exp / "run.py").write_text(
        "import time\n\n"
        'if __name__ == "__main__":\n    print("up", flush=True)\n    time.sleep(60)\n'
    )
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    job = client.post("/api/launch", json={"id": "script:slow/run.py"}).json()

    def status() -> str:
        return client.get(f"/api/launch/jobs/{job['id']}").json()["status"]

    for _ in range(100):
        if status() == "running":
            break
        time.sleep(0.1)
    client.post(f"/api/launch/jobs/{job['id']}/cancel", json={})
    for _ in range(100):
        if status() not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert status() == "cancelled"


def test_a_running_eval_reports_samples_done_of_its_total() -> None:
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.log import write_eval_log

    from louped import stores
    from louped.core import logs_dir

    task = Task(dataset=[Sample(input=f"q{i}", target="a") for i in range(5)])
    [log] = eval(task, model="mockllm/model", limit=3, log_dir=str(logs_dir()), display="none")
    log.status = "started"  # as a log reads while Inspect is still writing it
    write_eval_log(log)
    (run,) = stores.list_runs()
    assert (run.status, run.samples, run.total) == ("started", 3, 3)
