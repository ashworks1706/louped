"""Gates: the stop condition an experiment's README states, checked before the launches it guards.

    ---
    domain: honesty
    status: active
    gate:
      run: train.py              # the launch whose latest finished run supplies the metrics
      require:
        - heldout/caving < 0.954
      guards: [test.py]          # refused until every requirement holds
    chain: [sample.py, train.py, gate, test.py]
    ---

`run` and `guards` name a file in the experiment (train.py, sft.yaml, explore.ipynb) or any
launchable id (script:other/run.py). A requirement is `<metric> <op> <number>`, op one of
< <= > >= == !=, read without eval. The run is the newest finished MLflow run tagged with that
launch (`louped.launch`, which start_run writes). `chain` is the order `louped submit
<experiment> --chain` sends the steps to a cluster, `gate` standing for `louped gate`.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from typing import Any, cast

from louped.core import experiments_dir
from louped.stores.experiments import BadExperiment, declared
from louped.stores.mlflow_runs import list_runs
from louped.stores.types import GateCheck, GateStatus, Op, RunSummary

OPS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}  # fmt: skip
REQUIREMENT = re.compile(
    r"^\s*([\w.:/@-]+)\s*(<=|>=|==|!=|<|>)\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*$"
)
#: The chain step that runs `louped gate <experiment>` on the cluster.
GATE = "gate"


class BadGate(BadExperiment):
    """A gate or chain that does not parse; the message names the README and what is wrong."""


class GateClosed(ValueError):
    """A launch its experiment's gate holds back until every requirement passes."""


def _where(name: str) -> str:
    return f"experiments/{name}/README.md"


def launch_of(name: str, step: str) -> str:
    """The launchable id a gate or chain step names: an id as it is, else a file in the
    experiment, by its kind."""
    if ":" in step:
        return step
    path = experiments_dir() / name / step
    if "/" in step or not path.is_file():
        raise BadGate(f"{_where(name)}: {step!r} is not a file in experiments/{name}/")
    rel = f"{name}/{step}"
    if path.suffix == ".py":
        return f"script:{rel}"
    if path.suffix == ".ipynb":
        return f"notebook:{rel}"
    if path.suffix in (".yaml", ".yml"):
        head = path.read_text(encoding="utf-8").lstrip()
        if head.startswith("# louped train"):
            return f"train:{rel}"
        if head.startswith("# louped grid"):
            return f"grid:{rel}"
    raise BadGate(f"{_where(name)}: {step} is not a script, notebook, training config or grid")


def _strings(name: str, key: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BadGate(f"{_where(name)}: {key} is a list of strings, such as [test.py]")
    return value


def requirement(text: str) -> tuple[str, Op, float]:
    """A requirement's metric, op and threshold; ValueError saying the form when it is not one."""
    found = REQUIREMENT.match(text)
    if not found:
        raise ValueError(f"{text!r} is not '<metric> <op> <number>' with op one of {' '.join(OPS)}")
    return found[1], cast(Op, found[2]), float(found[3])


def spec(name: str) -> tuple[str, list[str], list[str]] | None:
    """The gate a README declares: its launch, requirements and guarded launches; None when it
    declares none. BadGate when it does not parse."""
    gate = declared(name, "gate")
    if gate is None:
        return None
    if not isinstance(gate, dict):
        raise BadGate(f"{_where(name)}: gate holds run, require and guards")
    if unknown := set(gate) - {"run", "require", "guards"}:
        raise BadGate(f"{_where(name)}: gate has unknown keys {sorted(unknown)}; "
                      "it holds run, require and guards")  # fmt: skip
    if not isinstance(gate.get("run"), str):
        raise BadGate(f"{_where(name)}: gate needs run, the launch whose runs it reads (train.py)")
    required = _strings(name, "gate.require", gate.get("require"))
    if not required:
        raise BadGate(f"{_where(name)}: gate.require lists at least one requirement")
    for text in required:
        try:
            requirement(text)
        except ValueError as exc:
            raise BadGate(f"{_where(name)}: gate.require: {exc}") from exc
    guards = _strings(name, "gate.guards", gate.get("guards", []))
    return launch_of(name, gate["run"]), required, [launch_of(name, g) for g in guards]


def _latest(launch: str, runs: list[RunSummary]) -> RunSummary | None:
    done = [r for r in runs if r.launch == launch and r.status == "finished"]
    return max(done, key=lambda r: r.created.timestamp() if r.created else 0.0, default=None)


def status(name: str, runs: list[RunSummary] | None = None) -> GateStatus | None:
    """An experiment's gate checked against the newest finished run of its launch; None when the
    README declares none. A gate that does not parse comes back with its error, not raised."""
    try:
        found = spec(name)
    except BadExperiment as exc:
        return GateStatus(launch="", run=None, guards=[], checks=[], passed=False, error=str(exc))
    if found is None:
        return None
    launch, required, guards = found
    run = _latest(launch, list_runs() if runs is None else runs)
    checks = []
    for text in required:
        metric, op, threshold = requirement(text)
        actual = run.metrics.get(metric) if run is not None else None
        passed = actual is not None and OPS[op](actual, threshold)
        checks.append(GateCheck(requirement=text, metric=metric, op=op, threshold=threshold,
                                actual=actual, passed=passed))  # fmt: skip
    return GateStatus(launch=launch, run=run.id if run else None, guards=guards, checks=checks,
                      passed=all(c.passed for c in checks))  # fmt: skip


def why(name: str, gate: GateStatus) -> str:
    """What holds a gate closed, in a line: its first failing requirement and the value."""
    if gate.run is None:
        return f"{name}'s gate reads {gate.launch}, which has no finished run yet"
    failing = next(c for c in gate.checks if not c.passed)
    value = "missing" if failing.actual is None else f"{failing.actual:g}"
    return f"{name}'s gate needs {failing.requirement}; it is {value} in run {gate.run}"


def guard(launch: str, chained_after: str | None = None) -> None:
    """Refuse (GateClosed) a launch an experiment's gate guards while that gate does not pass;
    BadGate when a gate that might guard it does not parse. chained_after names the experiment
    whose gate runs on the cluster right before this launch, which holds it there instead."""
    root = experiments_dir()
    folders = sorted(p.parent for p in root.glob("*/README.md")) if root.is_dir() else []
    runs: list[RunSummary] | None = None
    for folder in folders:
        found = spec(folder.name)
        if found is None or launch not in found[2] or folder.name == chained_after:
            continue
        runs = list_runs() if runs is None else runs
        gate = status(folder.name, runs)
        assert gate is not None
        if not gate.passed:
            raise GateClosed(f"{why(folder.name, gate)}. Edit the gate in "
                             f"{_where(folder.name)} to change it.")  # fmt: skip


def chain(name: str) -> list[str]:
    """The launch ids `chain:` lists in order, `gate` for the gate step; BadGate when it does not
    parse or names a gate the README does not declare."""
    steps = declared(name, "chain")
    if steps is None:
        raise BadGate(f"{_where(name)} declares no chain, such as chain: [train.py, gate, test.py]")
    steps = _strings(name, "chain", steps)
    if GATE in steps and spec(name) is None:
        raise BadGate(f"{_where(name)}: its chain has a gate step but it declares no gate")
    return [s if s == GATE else launch_of(name, s) for s in steps]
