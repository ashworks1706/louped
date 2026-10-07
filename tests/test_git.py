"""The project's git repository: a commit's file on its forge, and whether the commit is pushed."""

import subprocess
from pathlib import Path

import pytest

from louped.core.git import pushed_to, remote_url, top, tracked, web_url

SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:o/r.git",
        "git@github.com:o/r",
        "https://github.com/o/r",
        "https://github.com/o/r.git",
        "https://github.com/o/r/",
        "ssh://git@github.com/o/r",
        "ssh://git@github.com:22/o/r.git",
        "https://user@github.com/o/r.git",
    ],
)
def test_every_form_of_a_github_remote_gives_the_files_page_at_the_commit(remote: str) -> None:
    got = web_url(remote, SHA, "experiments/q/run.py")
    assert got == f"https://github.com/o/r/blob/{SHA}/experiments/q/run.py"
    assert web_url(remote, SHA) == f"https://github.com/o/r/tree/{SHA}"


def test_gitlab_and_bitbucket_map_too_and_other_hosts_do_not() -> None:
    assert web_url("git@gitlab.com:g/sub/r.git", SHA, "a.py") == (
        f"https://gitlab.com/g/sub/r/-/blob/{SHA}/a.py"
    )
    assert web_url("https://bitbucket.org/o/r.git", SHA, "a.py") == (
        f"https://bitbucket.org/o/r/src/{SHA}/a.py"
    )
    assert web_url("https://github.com/o/r", SHA, "my run.py") == (
        f"https://github.com/o/r/blob/{SHA}/my%20run.py"
    )
    for other in ("git@git.example.org:o/r.git", "/srv/git/r.git", "file:///srv/r.git",
                  "https://github.com/o"):  # fmt: skip
        assert web_url(other, SHA, "a.py") is None


def git(where: Path, *args: str) -> str:
    command = ["git", "-C", str(where), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def test_a_commit_is_pushed_once_a_remote_branch_holds_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    git(tmp_path, "init", "-q", "--bare", "origin.git")
    git(repo, "init", "-q", "-b", "main")
    (repo / "sub" / "run.py").write_text("print(1)\n")
    (repo / "loose.py").write_text("")
    git(repo, "add", "sub")
    git(repo, "commit", "-q", "-m", "x")
    sha = git(repo, "rev-parse", "HEAD")
    assert top(repo / "sub" / "run.py") == repo.resolve() and top(tmp_path) is None
    assert tracked(repo / "sub" / "run.py") == "sub/run.py"
    assert tracked(repo / "loose.py") is None and tracked(tmp_path / "x.py") is None
    assert remote_url(repo) is None  # no remote
    assert pushed_to(repo, sha) == []
    assert pushed_to(repo, "f" * 40) is None  # not here: cannot say
    git(repo, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(repo, "push", "-q", "origin", "main")
    assert pushed_to(repo, sha) == ["origin/main"]
    assert remote_url(repo, ["origin/main"]) == str(tmp_path / "origin.git")
