"""`louped init`: make a folder a research project.

It copies louped's templates (src/louped/templates): the project's louped.toml and AGENTS.md, the
MCP server, skills and prompt hook for a coding agent (the same files the Claude Code plugin
ships), and an example experiment. A file that exists is kept, never overwritten, so init is safe
to run again and in a repository that already has an AGENTS.md or a .mcp.json.
"""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"
EXAMPLE = "does-pushback-flip-answers"


def _files(example: bool) -> list[tuple[Path, str]]:
    """Each template file and where it goes in the project."""
    project = TEMPLATES / "project"
    agent = TEMPLATES / "agent"
    out = [
        (project / "louped.toml", "louped.toml"),
        (project / "AGENTS.md", "AGENTS.md"),
        (agent / ".mcp.json", ".mcp.json"),
        # the plugin's hooks, as the project's Claude Code settings: picks reach the agent
        (agent / "hooks" / "hooks.json", ".claude/settings.json"),
    ]
    out += [(f, f".claude/{f.relative_to(agent).as_posix()}")
            for f in sorted((agent / "skills").rglob("*")) if f.is_file()]  # fmt: skip
    if example:
        source = TEMPLATES / "example" / EXAMPLE
        out += [(f, f"experiments/{EXAMPLE}/{f.relative_to(source).as_posix()}")
                for f in sorted(source.rglob("*")) if f.is_file()]  # fmt: skip
    return out


def init(path: Path, example: bool = True) -> str:
    """The project at path, made or completed; what was written, what was kept, and what next."""
    root = path.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "experiments").mkdir(exist_ok=True)
    written: list[str] = []
    kept: list[str] = []
    for source, rel in _files(example):
        target = root / rel
        if target.exists():
            kept.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(rel)
    ignore = root / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    if not any(line.strip().rstrip("/") in (".louped", "/.louped") for line in lines):
        text = (TEMPLATES / "project" / "gitignore").read_text(encoding="utf-8")
        with ignore.open("a", encoding="utf-8") as out:
            out.write(("\n" if lines else "") + text)
        written.append(".gitignore" if not lines else ".gitignore (.louped/ added)")
    report = [f"louped project at {root}"]
    report += [f"  wrote {w}" for w in written]
    report += [f"  kept  {k} (it exists; compare it with louped's template)" for k in kept]
    report += ["", "Next:"]
    if path != Path("."):
        report.append(f"  cd {path}")
    report.append("  louped serve                 the app on http://127.0.0.1:8000")
    if example:
        report.append(f"  then Launch → {EXAMPLE} (tick tiny for an offline check)")
    report.append(
        "  and ask your coding agent to start a question: it reads AGENTS.md and .mcp.json"
    )
    return "\n".join(report)
