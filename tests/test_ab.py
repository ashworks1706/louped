"""Blind A/B: a person's picks of two eval runs' answers, sides hidden, and what they say."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_agent import call, tools
from test_judge import scripted, two_runs

from louped.judge import judge
from louped.server import create_app
from louped.stores import ab


def test_the_sides_are_hidden_but_stay_put_and_picks_come_back_as_a_or_b(tmp_path: Path) -> None:
    a, b = two_runs(["no", "no", "no", "no"], ["yes", "yes", "yes", "yes"])
    first = ab.session(a, b)
    assert len(first.pairs) == 4 and first.labelled == 0
    assert ab.session(a, b) == first  # the seed was saved: a reload shows the same sides
    sides = {p.sample: ("b" if p.left == "yes" else "a") for p in first.pairs}
    assert set(sides.values()) <= {"a", "b"}
    # the person picks "yes" every time, whichever side it sat on
    for p in first.pairs:
        ab.set_pick(a, b, p.sample, "left" if p.left == "yes" else "right")
    done = ab.session(a, b)
    assert done.labelled == 4
    assert all((p.pick == "left") == (p.left == "yes") for p in done.pairs)
    result = ab.result(a, b)
    assert (result.b_wins, result.a_wins, result.ties, result.total) == (4, 0, 0, 4)
    assert result.b_rate == 1 and result.low == result.high == 1
    ab.set_pick(a, b, first.pairs[0].sample, "tie")
    ab.set_pick(a, b, first.pairs[1].sample, None)
    result = ab.result(a, b)
    assert (result.labelled, result.ties, result.b_rate) == (3, 1, pytest.approx(2.5 / 3))
    assert result.low is not None and result.low < result.b_rate <= result.high  # type: ignore[operator]
    with pytest.raises(ValueError, match="share no answered sample 'x'"):
        ab.set_pick(a, b, "x", "left")
    with pytest.raises(ValueError, match="not an eval run id"):
        ab.session("../x", b)
    with pytest.raises(ValueError, match="not an eval run id"):
        ab.session(f"{a}\n", b)
    with pytest.raises(ValueError, match="not an eval run: e-nope"):
        ab.session("e-nope", b)
    assert sorted(p.name for p in (tmp_path / "home" / "ab").iterdir()) == [f"{a}~{b}.json"]


def test_a_judge_of_the_same_runs_is_checked_against_the_persons_picks(tmp_path: Path) -> None:
    a, b = two_runs(["no", "no"], ["yes", "yes"])
    run = judge(a, b, scripted("Verdict: 2", "Verdict: 1", "Verdict: 1", "Verdict: 2"))
    for p in ab.session(a, b).pairs:
        ab.set_pick(a, b, p.sample, "left" if p.left == "yes" else "right")
    [j] = ab.result(a, b).judges
    assert j.run == run and j.labelled == 2
    assert j.agreement == 0.5  # one pair B in both orders, one a position-following tie


def test_blind_ab_through_the_api_and_mcp(tmp_path: Path) -> None:
    a, b = two_runs(["no"], ["yes"])
    api = TestClient(create_app(launching=True), base_url="http://localhost")
    [pair] = api.get("/api/ab", params={"a": a, "b": b}).json()["pairs"]
    side = "left" if pair["left"] == "yes" else "right"
    picked = api.post("/api/ab/pick", json={"a": a, "b": b, "sample": pair["sample"], "side": side})
    assert picked.json()["labelled"] == 1
    assert call(tools(), "ab_results", a=a, b=b)["b_rate"] == 1
    assert api.get("/api/ab", params={"a": "m-1", "b": b}).status_code == 400
    readonly = TestClient(create_app(launching=False), base_url="http://localhost")
    assert readonly.get("/api/ab", params={"a": a, "b": b}).status_code == 403
    assert readonly.get("/api/ab/result", params={"a": a, "b": b}).json()["labelled"] == 1
