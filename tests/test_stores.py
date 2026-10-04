from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import generate

from louped import stores
from louped.core import logs_dir
from louped.server import create_app
from louped.stores.experiments import (
    DEFAULT_DOMAINS,
    BadExperiment,
    front_matter,
    question,
    result,
)
from louped.tracking import start_run
from louped.tracking.runs import log_json


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


README = (
    "---\ndomain: {domain}\nstatus: {status}\n---\n\n"
    "# x\n\n## Question\n\n{q}\n\n## Result\n\n{r}\n"
)


def write_experiment(root: Path, name: str, domain: str, status: str = "parked") -> None:
    folder = root / "experiments" / name
    folder.mkdir(parents=True)
    text = README.format(domain=domain, status=status, q="Does it cave?", r="It caves.")
    (folder / "README.md").write_text(text)


def test_experiments_group_runs_by_tag(tmp_path: Path) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    run_eval(["yes"], tags=["experiment:pressure"])
    run_eval(["yes"])
    [exp] = stores.list_experiments()
    assert exp.question == "Does it cave?"
    assert exp.result == "It caves."
    assert (exp.axis, exp.domain, exp.status) == ("behavior", "honesty", "active")
    assert exp.domain_title == DEFAULT_DOMAINS["honesty"][1]
    assert len(exp.runs) == 1


def test_experiments_sort_by_domain_then_active(tmp_path: Path) -> None:
    write_experiment(tmp_path, "a-kernels", "inference", "answered")
    write_experiment(tmp_path, "b-probe", "mechanisms", "parked")
    write_experiment(tmp_path, "c-probe", "mechanisms", "active")
    assert [e.name for e in stores.list_experiments()] == ["c-probe", "b-probe", "a-kernels"]


def test_a_folder_without_a_readme_is_not_an_experiment(tmp_path: Path) -> None:
    write_experiment(tmp_path, "kept", "honesty")
    (tmp_path / "experiments" / "deleted" / "__pycache__").mkdir(parents=True)
    assert [e.name for e in stores.list_experiments()] == ["kept"]
    with pytest.raises(stores.NotFound):
        stores.get_experiment("deleted")


def test_front_matter_is_required_and_checked() -> None:
    with pytest.raises(BadExperiment, match="no front matter"):
        front_matter("# x\n\n## Question\n\nWhy?\n", "x")
    with pytest.raises(BadExperiment, match="domain 'physics'"):
        front_matter("---\ndomain: physics\nstatus: active\n---\n", "x")
    with pytest.raises(BadExperiment, match="status 'done'"):
        front_matter("---\ndomain: context\nstatus: done\n---\n", "x")
    assert front_matter("---\ndomain: context\nstatus: active\n---\n", "x") == ("context", "active")


def test_the_example_experiment_init_ships_is_filed(monkeypatch: pytest.MonkeyPatch) -> None:
    example = Path(__file__).parents[1] / "src" / "louped" / "templates" / "example"
    monkeypatch.setenv("LOUPED_EXPERIMENTS", str(example))
    experiments = stores.list_experiments()
    assert experiments
    assert all(e.question for e in experiments)


def test_question_and_result_parsing() -> None:
    assert question("## Question\n\nOne\nline.\n\n## Next") == "One line."
    assert question("# nothing here") is None
    assert result("## Result\n\nNot run yet.\n") == "Not run yet."
    assert result("## Result\n\nWith `--tiny`: 0.5.\n") == "With --tiny: 0.5."
    assert result("## Result\n\n## Next\n\nLater.\n") is None
    assert question("## Question\n\n<!-- a hint -->\n\n## Observation\n") is None


def test_one_experiment_carries_its_readme(tmp_path: Path) -> None:
    write_experiment(tmp_path, "pressure", "honesty", "active")
    client = TestClient(create_app(), base_url="http://localhost")
    body = client.get("/api/experiments/pressure").json()
    assert body["question"] == "Does it cave?"
    assert body["readme"].startswith("# x")
    assert "domain:" not in body["readme"]
    assert "## Question" not in body["readme"] and "## Result" not in body["readme"]
    assert body["result"] == "It caves."
    assert client.get("/api/experiments/nope").status_code == 404


def test_a_bad_readme_names_its_folder_through_the_api(tmp_path: Path) -> None:
    folder = tmp_path / "experiments" / "stray"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# stray\n")
    res = TestClient(create_app(), base_url="http://localhost").get("/api/experiments")
    assert res.status_code == 500
    assert "experiments/stray" in res.json()["detail"]


def test_api_404s_and_samples() -> None:
    run_eval(["yes"])
    client = TestClient(create_app(), base_url="http://localhost")
    [run] = client.get("/api/runs").json()
    assert client.get(f"/api/runs/{run['id']}/samples").json()[0]["scores"] == {"includes": 1.0}
    assert client.get("/api/runs/e-missing").status_code == 404
    assert client.get(f"/api/runs/{run['id']}/samples/99").status_code == 404


def test_views_skip_bad_files_and_vectors_read_without_torch() -> None:
    import torch

    from louped.analysis import heatmap, line
    from louped.tracking import log_json
    from louped.vectors import save_vector

    with start_run("interp", name="views") as run:
        log_json(line("scores", [0.0, 1.0], {"a": [1.0, 2.0]}, "layer", "score"), "views/0.json")
        log_json(heatmap("patch", [[0.5]], ["p"], ["0"], "pos", "layer"), "views/1.json")
        log_json({"kind": "pie"}, "views/2.json")
    save_vector("dir", torch.ones(3), model="m", layer=2, method="diff-in-means")

    client = TestClient(create_app(), base_url="http://localhost")
    views = client.get(f"/api/runs/m-{run.info.run_id}/views").json()
    assert [v["view"]["kind"] for v in views] == ["line", "heatmap"]
    detail = client.get(f"/api/runs/m-{run.info.run_id}").json()
    assert "views/1.json" in [a["path"] for a in detail["artifacts"]]
    (vector,) = client.get("/api/vectors").json()
    assert (vector["name"], vector["layer"], vector["dim"]) == ("dir", 2, 3)
    assert client.get("/api/runs/m-missing/views").status_code == 404


def test_paired_comparison_counts_flips_and_brackets_the_difference() -> None:
    run_eval(["yes", "no", "no", "no", "yes", "no"], tags=["side:a"])
    run_eval(["yes", "yes", "yes", "no", "no", "yes"], tags=["side:b"])
    first, second = sorted(stores.list_runs(), key=lambda r: list(stores.get_run(r.id).tags))
    result = stores.compare(first.id, second.id)
    [score] = result.scores
    assert (score.name, score.n, score.up, score.down) == ("includes", 6, 3, 1)
    assert abs(score.diff - 2 / 6) < 1e-9 and abs(score.mean_b - score.mean_a - score.diff) < 1e-9
    assert score.low <= score.diff <= score.high
    assert result == stores.compare(first.id, second.id)  # seeded
    client = TestClient(create_app(), base_url="http://localhost")
    body = client.get("/api/compare", params={"a": first.id, "b": second.id}).json()
    assert body["scores"][0]["up"] == 3
    assert client.get("/api/compare", params={"a": first.id, "b": "e-nope"}).status_code == 404
