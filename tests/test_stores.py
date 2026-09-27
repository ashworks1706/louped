from pathlib import Path

from fastapi.testclient import TestClient
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import generate

from loupe import stores
from loupe.core import logs_dir
from loupe.server import create_app
from loupe.stores.experiments import question
from loupe.tracking import start_run
from loupe.tracking.runs import log_json


def run_eval(answers: list[str], tags: list[str] | None = None) -> None:
    outputs = [ModelOutput.from_content("mockllm/model", a) for a in answers]
    task = Task(
        dataset=[Sample(id=i + 1, input=f"q{i}", target="yes") for i in range(len(answers))],
        solver=generate(),
        scorer=includes(),
    )
    eval(
        task,
        model=get_model("mockllm/model", custom_outputs=outputs),
        log_dir=str(logs_dir()),
        tags=tags or [],
        display="none",
    )


def test_empty_home_lists_nothing() -> None:
    assert stores.list_runs() == []
    assert stores.list_experiments() == []


def test_eval_log_run_samples_and_transcript() -> None:
    run_eval(["yes", "no", "yes"])
    [run] = stores.list_runs()
    assert run.kind == "eval"
    assert run.samples == 3
    assert abs(run.metrics["includes/accuracy"] - 2 / 3) < 1e-9

    samples = stores.list_samples(run.id)
    assert [s.scores["includes"] for s in samples] == [1.0, 0.0, 1.0]

    detail = stores.get_sample(run.id, "2")
    assert [m.role for m in detail.messages] == ["user", "assistant"]
    assert detail.messages[1].text == "no"
    assert detail.scores[0].raw == "I"


def test_mlflow_run_with_history_and_artifact() -> None:
    with start_run("probe-study", name="layer sweep", params={"model": "tiny"}) as active:
        import mlflow

        for step, acc in enumerate([0.5, 0.7, 0.9]):
            mlflow.log_metric("probe_acc", acc, step=step)
        log_json({"rows": [[1, 2]]}, "tables/probe.json")

    [run] = stores.list_runs()
    assert run.id == "m-" + active.info.run_id
    assert run.experiment == "probe-study"
    detail = stores.get_run(run.id)
    assert [p.value for p in detail.history["probe_acc"]] == [0.5, 0.7, 0.9]
    assert {"meta.json"} <= {a.path for a in detail.artifacts}
    assert detail.params["model"] == "tiny"


def test_experiments_group_runs_by_tag(tmp_path: Path) -> None:
    folder = tmp_path / "experiments" / "pressure"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# pressure\n\n## Question\n\nDoes it cave?\n\n## Result\n")
    run_eval(["yes"], tags=["experiment:pressure"])
    run_eval(["yes"])
    [exp] = stores.list_experiments()
    assert exp.question == "Does it cave?"
    assert len(exp.runs) == 1


def test_question_parsing() -> None:
    assert question("## Question\n\nOne\nline.\n\n## Next") == "One line."
    assert question("# nothing here") is None


def test_api_404s_and_samples() -> None:
    run_eval(["yes"])
    client = TestClient(create_app())
    [run] = client.get("/api/runs").json()
    assert client.get(f"/api/runs/{run['id']}/samples").json()[0]["scores"] == {"includes": 1.0}
    assert client.get("/api/runs/e-missing").status_code == 404
    assert client.get(f"/api/runs/{run['id']}/samples/99").status_code == 404


def test_views_skip_bad_files_and_vectors_read_without_torch() -> None:
    import torch

    from loupe.analysis import heatmap, line
    from loupe.tracking import log_json
    from loupe.vectors import save_vector

    with start_run("interp", name="views") as run:
        log_json(line("scores", [0.0, 1.0], {"a": [1.0, 2.0]}, "layer", "score"), "views/0.json")
        log_json(heatmap("patch", [[0.5]], ["p"], ["0"], "pos", "layer"), "views/1.json")
        log_json({"kind": "pie"}, "views/2.json")
    save_vector("dir", torch.ones(3), model="m", layer=2, method="diff-in-means")

    client = TestClient(create_app())
    views = client.get(f"/api/runs/m-{run.info.run_id}/views").json()
    assert [v["view"]["kind"] for v in views] == ["line", "heatmap"]
    detail = client.get(f"/api/runs/m-{run.info.run_id}").json()
    assert "views/1.json" in [a["path"] for a in detail["artifacts"]]
    (vector,) = client.get("/api/vectors").json()
    assert (vector["name"], vector["layer"], vector["dim"]) == ("dir", 2, 3)
    assert client.get("/api/runs/m-missing/views").status_code == 404
