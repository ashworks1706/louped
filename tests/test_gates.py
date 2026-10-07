"""An experiment's gate: parsed strictly, checked against its launch's newest finished run, and
holding back the launches it guards until it passes."""

import sys
from pathlib import Path

import mlflow
import pytest
from fastapi.testclient import TestClient

from louped import cli
from louped.server import create_app
from louped.stores import gates
from louped.stores.gates import BadGate, GateClosed
from louped.tracking import start_run
from louped.tracking.runs import launch

GATE = """---
domain: honesty
status: active
gate:
  run: train.py
  require:
    - heldout/caving < 0.954
    - heldout/n >= 100
  guards: [test.py]
---
# caving
"""
SCRIPT = 'if __name__ == "__main__":\n    print("ran")\n'


@pytest.fixture
def caving(tmp_path: Path) -> Path:
    folder = tmp_path / "experiments" / "caving"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(GATE)
    for name in ("train.py", "test.py"):
        (folder / name).write_text(SCRIPT)
    return folder


def trained(monkeypatch: pytest.MonkeyPatch, caving: float, n: float = 200) -> None:
    """A finished run of train.py, as a job would make it."""
    monkeypatch.setenv("LOUPED_LAUNCH", "script:caving/train.py")
    with start_run("caving"):
        mlflow.log_metrics({"heldout/caving": caving, "heldout/n": n})
    monkeypatch.delenv("LOUPED_LAUNCH")


def test_requirements_parse_strictly() -> None:
    assert gates.requirement("heldout/caving < 0.954") == ("heldout/caving", "<", 0.954)
    assert gates.requirement("loss>=1e-3") == ("loss", ">=", 0.001)
    assert gates.requirement(" acc != -2 ") == ("acc", "!=", -2.0)
    for bad in ("caving < 0.9 or True", "caving <> 1", "caving < x", "__import__('os') < 1",
                "caving < 1; rm -rf ~", "< 1"):  # fmt: skip
        with pytest.raises(ValueError, match="is not '<metric> <op> <number>'"):
            gates.requirement(bad)


def test_a_gate_that_does_not_parse_says_what_is_wrong(caving: Path) -> None:
    readme = caving / "README.md"
    cases = {
        "  require: [caving < x]\n": "gate.require: 'caving < x' is not",
        "  requires: [a < 1]\n": "unknown keys ['requires']",
        "  require: []\n": "at least one requirement",
        "  require: [a < 1]\n  guards: test.py\n": "gate.guards is a list of strings",
    }
    for body, said in cases.items():
        readme.write_text(
            f"---\ndomain: honesty\nstatus: active\ngate:\n  run: train.py\n{body}---\n"
        )
        with pytest.raises(BadGate, match=said.replace("[", r"\[").replace("]", r"\]")):
            gates.spec("caving")
        status = gates.status("caving")
        assert status is not None and status.error and not status.passed
    readme.write_text("---\ndomain: honesty\nstatus: active\ngate:\n  run: missing.py\n"
                      "  require: [a < 1]\n---\n")  # fmt: skip
    with pytest.raises(BadGate, match=r"'missing\.py' is not a file in experiments/caving/"):
        gates.spec("caving")
    readme.write_text("---\ndomain: honesty\nstatus: active\n---\n")
    assert gates.status("caving") is None


def test_a_gate_reads_the_newest_finished_run_of_its_launch(
    caving: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = gates.status("caving")
    assert gate is not None and gate.run is None and not gate.passed
    assert gate.launch == "script:caving/train.py" and gate.guards == ["script:caving/test.py"]
    trained(monkeypatch, 0.97)
    gate = gates.status("caving")
    assert gate is not None and gate.run is not None and not gate.passed
    assert [(c.actual, c.passed) for c in gate.checks] == [(0.97, False), (200, True)]
    with start_run("caving"):  # a run another launch made does not count
        mlflow.log_metrics({"heldout/caving": 0.5, "heldout/n": 200})
    trained(monkeypatch, 0.95)
    gate = gates.status("caving")
    assert gate is not None and gate.passed and gate.checks[0].actual == 0.95


def test_a_script_run_from_a_shell_is_its_launch(
    caving: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOUPED_LAUNCH", raising=False)
    monkeypatch.setattr(sys, "argv", [str(caving / "train.py")])
    assert launch() == "script:caving/train.py"
    monkeypatch.setattr(sys, "argv", ["/usr/bin/louped", "train"])
    assert launch() is None
    monkeypatch.setenv("LOUPED_LAUNCH", "train:caving/sft.yaml")
    assert launch() == "train:caving/sft.yaml"


def test_a_guarded_launch_is_refused_until_the_gate_passes(
    caving: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TestClient(create_app(launching=True), base_url="http://localhost")
    body = {"id": "script:caving/test.py", "options": {}}
    trained(monkeypatch, 0.9612)
    refused = api.post("/api/launch", json=body)
    assert refused.status_code == 409
    said = refused.json()["detail"]
    assert "heldout/caving < 0.954" in said and "0.9612" in said and "README.md" in said
    exported = api.post("/api/launch/export", json={**body, "target": {"provider": "sol"}})
    assert exported.status_code == 409
    gate = api.get("/api/experiments/caving").json()["gate"]
    assert gate["passed"] is False and gate["checks"][0]["actual"] == 0.9612
    assert api.post("/api/launch", json={"id": "script:caving/train.py"}).status_code == 200

    trained(monkeypatch, 0.93)
    assert api.post("/api/launch", json=body).status_code == 200
    assert api.get("/api/experiments/caving").json()["gate"]["passed"] is True


def test_louped_gate_prints_each_requirement_and_exits_by_it(
    caving: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def gate() -> object:
        monkeypatch.setattr(sys, "argv", ["louped", "gate", "caving"])
        with pytest.raises(SystemExit) as done:
            cli.main()
        return done.value.code

    trained(monkeypatch, 0.97, n=50)
    assert gate() == 1
    out = capsys.readouterr().out
    assert "FAIL  heldout/caving < 0.954" in out and "0.97" in out
    assert "FAIL  heldout/n >= 100" in out and "FAIL: script:caving/test.py waits." in out
    trained(monkeypatch, 0.9, n=150)
    assert gate() == 0
    assert "PASS: script:caving/test.py may run." in capsys.readouterr().out


def test_a_chain_lists_its_steps_and_needs_a_gate_for_its_gate_step(caving: Path) -> None:
    readme = caving / "README.md"
    readme.write_text(GATE.replace("---\n# caving", "chain: [train.py, gate, test.py]\n---\n"))
    assert gates.chain("caving") == ["script:caving/train.py", "gate", "script:caving/test.py"]
    readme.write_text("---\ndomain: honesty\nstatus: active\nchain: [train.py, gate]\n---\n")
    with pytest.raises(BadGate, match="declares no gate"):
        gates.chain("caving")
    readme.write_text(GATE)
    with pytest.raises(GateClosed, match="no finished run"):
        gates.guard("script:caving/test.py")
    gates.guard("script:caving/test.py", chained_after="caving")  # held on the cluster instead
