import json
import subprocess
from pathlib import Path

from loupe.core import capture
from loupe.core.meta import git_state, packages


def test_packages_records_missing_as_none() -> None:
    found = packages(("pydantic", "surely-not-installed-pkg"))
    assert found["pydantic"]
    assert found["surely-not-installed-pkg"] is None


def test_git_state_outside_a_repo(tmp_path: Path) -> None:
    state = git_state(tmp_path)
    assert state.sha is None


def test_git_state_reads_sha_and_dirty(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    clean = git_state(tmp_path)
    assert clean.sha is not None and len(clean.sha) == 40
    assert not clean.dirty

    (tmp_path / "f.txt").write_text("changed")
    assert git_state(tmp_path).dirty


def test_capture_writes_json(tmp_path: Path) -> None:
    meta = capture(seed=7, cwd=tmp_path)
    out = tmp_path / "run" / "meta.json"
    meta.write(out)
    data = json.loads(out.read_text())
    assert data["seed"] == 7
    assert "loupelab" in data["packages"]
