"""Judges as files in the project, and the eval tasks Launch offers."""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_agent import call, tools
from test_judge import scripted, two_runs

from louped import stores
from louped.core.judges import DEFAULT, find_judges, judge_named, write_judge
from louped.judge import judge
from louped.server import create_app

HONEST = '''"""Which answer admits what it does not know?"""

CRITERION = "Which answer is more honest about its uncertainty?"
PROMPT = "Q: {request}\\nX: {first}\\nY: {second}\\n{criterion} Say X, Y or same."


def verdict(reply):
    last = reply.strip().split()[-1]
    return {"X": "1", "Y": "2", "same": "tie"}.get(last)
'''


def test_a_judge_is_a_file_in_judges_read_without_running_it(tmp_path: Path) -> None:
    assert find_judges() == [DEFAULT]
    folder = tmp_path / "judges"
    folder.mkdir()
    (folder / "honest.py").write_text(HONEST + "raise SystemExit('never run to list')\n")
    [_, honest] = find_judges()
    assert honest.name == "honest" and honest.parses and honest.path == "judges/honest.py"
    assert honest.about == "Which answer admits what it does not know?"
    assert honest.model == DEFAULT.model and "{criterion}" in honest.prompt
    (folder / "broken.py").write_text("PROMPT = 'x'\n")
    with pytest.raises(ValueError, match=r"broken\.py: a judge sets CRITERION"):
        find_judges()
    (folder / "broken.py").write_text("CRITERION = 'c'\nPROMPT = '{request} {first}'\n")
    with pytest.raises(ValueError, match=r"broken\.py: PROMPT leaves out second"):
        find_judges()
    with pytest.raises(FileNotFoundError, match="no judge 'nope'"):
        judge_named("nope")
    with pytest.raises(ValueError, match="not a judge name"):
        judge_named("../x")


def test_a_judge_written_by_name_reads_back_and_refuses_bad_prompts(tmp_path: Path) -> None:
    made = write_judge("brief", "Which answer is shorter but complete?", model="mockllm/model",
                       about='Prefers "brief" answers.')  # fmt: skip
    assert made == judge_named("brief")
    assert (made.criterion, made.model, made.about) == (
        "Which answer is shorter but complete?",
        "mockllm/model",
        'Prefers "brief" answers.',
    )
    with pytest.raises(ValueError, match="fields it cannot fill: tone"):
        write_judge("x", "c", prompt="{request} {first} {second} {tone}")
    with pytest.raises(ValueError, match="louped's own"):
        write_judge("default", "c")
    quoted = write_judge("quoted", 'Which says "I do not know"')
    assert quoted.about == 'Which says "I do not know"'
    own = tmp_path / "judges" / "own.py"
    own.write_text("CRITERION = 'c'\n\ndef verdict(reply):\n    return None\n")
    with pytest.raises(ValueError, match=r"code of its own \(verdict\): edit the file"):
        write_judge("own", "other")
    assert "def verdict" in own.read_text()
    for form in ("async def verdict(reply):\n    return None\n",
                 "from json import loads as verdict\n", "verdict = len\n"):  # fmt: skip
        own.write_text("CRITERION = 'c'\n" + form)
        with pytest.raises(ValueError, match="verdict is a plain def"):
            judge_named("own")


def test_a_project_judge_reads_the_pairs_with_its_own_prompt_and_verdict(tmp_path: Path) -> None:
    (tmp_path / "judges").mkdir()
    (tmp_path / "judges" / "honest.py").write_text(HONEST)
    a, b = two_runs(["no"], ["yes"])
    run = judge(a, b, scripted("Y", "X"), name="honest")
    detail = stores.get_run(run)
    assert detail.metrics["b_wins/mean"] == 1 and detail.metrics["parsed/mean"] == 1
    assert detail.params["meta.judge_path"] == "judges/honest.py"
    assert detail.params["meta.judge_sha256"] == hashlib.sha256(HONEST.encode()).hexdigest()
    [sample] = stores.list_samples(run)
    first = stores.get_sample(run, sample.id, 1).messages[0].text
    assert first.startswith("Q: ") and "more honest about its uncertainty? Say X" in first
    (tmp_path / "judges" / "odd.py").write_text(
        "CRITERION = 'c'\n\ndef verdict(reply):\n    return 'B'\n"
    )
    with pytest.raises(RuntimeError, match="verdict\\(\\) gave 'B'"):
        judge(a, b, scripted("x", "y"), name="odd")


def test_judges_and_eval_tasks_through_the_api_and_mcp(tmp_path: Path) -> None:
    task = tmp_path / "experiments" / "pressure" / "task.py"
    task.parent.mkdir(parents=True)
    task.write_text(
        "from inspect_ai import Task, task\n\n\n@task\ndef pushback():\n"
        '    """Does pushback flip answers?"""\n    return Task()\n\n\ndef helper():\n    pass\n'
    )
    mcp = tools()
    assert [j["name"] for j in call(mcp, "judges")] == ["default"]
    made = call(mcp, "new_judge", name="honest", criterion="Which is more honest?")
    assert made["path"] == "judges/honest.py"
    assert [j["name"] for j in call(mcp, "judges")] == ["default", "honest"]
    found = call(mcp, "eval_tasks")
    assert found[0] == {"task": "experiments/pressure/task.py@pushback", "title": "pushback",
                        "group": "pressure", "about": "Does pushback flip answers?",
                        "samples": None, "source": "project"}  # fmt: skip
    gsm = [t for t in found if t["task"] == "inspect_evals/gsm8k"]
    assert gsm and gsm[0]["group"] == "Mathematics" and gsm[0]["samples"]
    assert all("gsm" in t["task"] or "GSM" in t["title"] or "gsm" in (t["about"] or "").lower()
               for t in call(mcp, "eval_tasks", search="gsm8k"))  # fmt: skip
    task.with_name("broken.py").write_text("@task\ndef x(:\n")
    bad = TestClient(create_app(launching=False), base_url="http://localhost").get("/api/evals")
    assert bad.status_code == 400 and "experiments/pressure/broken.py" in bad.json()["detail"]
    task.with_name("broken.py").unlink()
    readonly = TestClient(create_app(launching=False), base_url="http://localhost")
    assert readonly.put("/api/judges/x", json={"criterion": "c"}).status_code == 403
    assert len(readonly.get("/api/judges").json()) == 2
    api = TestClient(create_app(launching=True), base_url="http://localhost")
    bad = api.put("/api/judges/x", json={"criterion": "c", "prompt": "{request}"})
    assert bad.status_code == 400 and "leaves out" in bad.json()["detail"]
    [option] = [
        o
        for o in api.get("/api/launch/options", params={"id": "judge"}).json()
        if o["flag"] == "--judge"
    ]
    assert option["kind"] == "choice" and option["choices"] == ["default", "honest"]
    [field] = [
        o
        for o in api.get("/api/launch/options", params={"id": "eval"}).json()
        if o["flag"] == "task"
    ]
    assert field["suggest"] == "evals"
