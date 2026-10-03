"""Pairwise judging over two eval runs, with a scripted judge."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from inspect_ai.model import ModelOutput, get_model
from test_stores import run_eval

from loupe import stores
from loupe.inspect_ext.judge import verdict
from loupe.judge import judge
from loupe.server import create_app
from loupe.stores.labels import kappa


def scripted(*replies: str):
    outputs = [ModelOutput.from_content("mockllm/model", r) for r in replies]
    return get_model("mockllm/model", custom_outputs=outputs)


def two_runs(a: list[str], b: list[str]) -> tuple[str, str]:
    ids: list[str] = []
    for answers in (a, b):
        run_eval(answers, tags=["experiment:pressure"])
        [new] = {r.id for r in stores.list_runs()} - set(ids)
        ids.append(new)
    return ids[0], ids[1]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [("B is clearer.\nVerdict: 2", "2"), ("**Verdict:** tie", "tie"),
     ("Verdict: 1 ... on reflection, Verdict: 2", "2"), ("Answer 2 is better.", None)],
)  # fmt: skip
def test_the_verdict_is_the_last_verdict_line(reply: str, expected: str | None) -> None:
    assert verdict(reply) == expected


def test_a_judge_that_prefers_b_in_both_orders_gives_b_the_win(tmp_path: Path) -> None:
    a, b = two_runs(["no"], ["yes"])
    run = judge(a, b, scripted("Verdict: 2", "Verdict: 1"))
    detail = stores.get_run(run)
    assert detail.experiment == "pressure"
    assert detail.metrics["b_wins/mean"] == 1
    assert detail.metrics["consistent/mean"] == 1 and detail.metrics["parsed/mean"] == 1
    [sample] = stores.list_samples(run)
    full = stores.get_sample(run, sample.id, 1)
    assert [m.role for m in full.messages] == ["user", "assistant"] * 2
    assert "[Answer 1]\nno" in full.messages[0].text and "[Answer 1]\nyes" in full.messages[2].text


def test_a_judge_that_follows_position_or_gives_no_verdict_shows_it(tmp_path: Path) -> None:
    a, b = two_runs(["no"], ["yes"])
    detail = stores.get_run(judge(a, b, scripted("Verdict: 1", "Answer 2.")))
    assert detail.metrics["b_wins/mean"] == 0.25
    assert detail.metrics["consistent/mean"] == 0 and detail.metrics["parsed/mean"] == 0.5


def test_only_samples_both_runs_answered_are_judged(tmp_path: Path) -> None:
    a, b = two_runs(["no", "yes", "no"], ["yes", "yes"])
    run = judge(a, b, scripted(*["Verdict: tie"] * 4))
    assert {s.id for s in stores.list_samples(run)} == {"1", "2"}
    assert stores.get_run(run).metrics["b_wins/mean"] == 0.5


def test_judging_a_run_that_is_not_an_eval_names_it() -> None:
    with pytest.raises(ValueError, match="not an eval run: m-123"):
        judge("m-123", "e-456")


def test_a_persons_labels_give_the_judges_agreement_and_kappa(tmp_path: Path) -> None:
    a, b = two_runs(["no", "no", "no"], ["yes", "yes", "yes"])
    run = judge(a, b, scripted(*["Verdict: 2"] * 6))  # position-following: every pair a tie
    client = TestClient(create_app(launching=True), base_url="http://localhost")
    assert client.get(f"/api/runs/{run}/agreement").json()["labelled"] == 0
    for sample, label in (("1", "tie"), ("2", "tie"), ("3", "b")):
        put = client.post(f"/api/runs/{run}/labels/{sample}", json={"label": label})
        assert put.status_code == 200, put.text
    got = client.get(f"/api/runs/{run}/agreement").json()
    assert (got["labelled"], got["total"]) == (3, 3)
    assert got["agreement"] == pytest.approx(2 / 3) and got["kappa"] == pytest.approx(0)
    client.post(f"/api/runs/{run}/labels/3", json={"label": None})
    assert client.get(f"/api/runs/{run}/labels").json() == {"1": "tie", "2": "tie"}
    assert client.post(f"/api/runs/{run}/labels/9", json={"label": "a"}).status_code == 400
    assert client.get(f"/api/runs/{a}/agreement").status_code == 400  # not a judge run
    exposed = TestClient(create_app(), base_url="http://localhost")
    assert exposed.post(f"/api/runs/{run}/labels/1", json={"label": "a"}).status_code == 403


@pytest.mark.parametrize(
    ("pairs", "expected"),
    [([("a", "a"), ("b", "b")], 1.0), ([("a", "b"), ("b", "a")], -1.0),
     ([("a", "a"), ("a", "a")], None)],
)  # fmt: skip
def test_kappa_is_agreement_beyond_chance(
    pairs: list[tuple[str, str]], expected: float | None
) -> None:
    assert kappa(pairs) == expected
