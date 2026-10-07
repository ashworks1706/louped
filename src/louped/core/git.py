"""The project's git repository: its commands, where a commit is pushed, and a file's page at a
commit on the forge that hosts it (GitHub, GitLab or Bitbucket)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit

#: The forges whose web pages are known, by host: a file's page and a commit's tree.
FORGES = {
    "github.com": ("{base}/blob/{sha}/{path}", "{base}/tree/{sha}"),
    "gitlab.com": ("{base}/-/blob/{sha}/{path}", "{base}/-/tree/{sha}"),
    "bitbucket.org": ("{base}/src/{sha}/{path}", "{base}/src/{sha}"),
}
#: git@host:owner/repo(.git), scp-like.
SCP = re.compile(r"^[\w.-]+@([\w.-]+):(.+)$")


def git(where: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """git in where's repository; OSError when git is not installed."""
    return subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True,
                          timeout=30)  # fmt: skip


def top(where: Path) -> Path | None:
    """The root of the repository holding where; None outside one or without git."""
    try:
        found = git(where if where.is_dir() else where.parent, "rev-parse", "--show-toplevel")
    except OSError:
        return None
    return Path(found.stdout.strip()).resolve() if found.returncode == 0 else None


def tracked(path: Path) -> str | None:
    """path relative to its repository's root, when git tracks it; else None."""
    try:
        found = git(path.parent, "ls-files", "--full-name", "--", path.name)
    except OSError:
        return None
    name = found.stdout.strip()
    return name if found.returncode == 0 and name and "\n" not in name else None


def pushed_to(root: Path, commit: str) -> list[str] | None:
    """The remote branches holding commit (origin/main); None when this repository does not
    have the commit, so cannot say."""
    found = git(root, "branch", "-r", "--contains", commit, "--format=%(refname:short)")
    if found.returncode != 0:
        return None
    return [b for b in found.stdout.split() if "/" in b and not b.endswith("/HEAD")]


def remote_url(root: Path, branches: list[str] | None = None) -> str | None:
    """The URL of the remote holding one of branches, else origin, else the only remote."""
    names = git(root, "remote").stdout.split()
    held = [b.split("/")[0] for b in branches or [] if b.split("/")[0] in names]
    name = (
        held[0]
        if held
        else "origin"
        if "origin" in names
        else names[0]
        if len(names) == 1
        else None
    )
    if name is None:
        return None
    return git(root, "remote", "get-url", name).stdout.strip() or None


def web_url(remote: str, commit: str, path: str | None = None) -> str | None:
    """The page of path (or of the whole tree) at commit on the forge remote points at, for
    github.com, gitlab.com and bitbucket.org; None for any other host or a local path."""
    if found := SCP.match(remote):
        host, repo = found.groups()
    else:
        parts = urlsplit(remote)
        if parts.scheme not in ("https", "http", "ssh", "git"):
            return None
        host, repo = parts.hostname or "", parts.path
    repo = repo.strip("/").removesuffix(".git")
    if host not in FORGES or repo.count("/") < 1:
        return None
    page, tree = FORGES[host]
    base = f"https://{host}/{repo}"
    if path is None:
        return tree.format(base=base, sha=commit)
    return page.format(base=base, sha=commit, path=quote(path))
