"""louped check: the mechanical half of grounding. In the project's Markdown, every result number
sits beside what it came from, every citation names a page with a passage pinned on it, every
ref resolves; and every pin is still on its page.

What counts as a result number is exact so the check never guesses: a decimal (0.92), a
percentage (78%) or a fraction (12/40). Whole numbers (3 conditions, 2024) are not checked. A
number is sourced when its paragraph or list item (a table: with the paragraph above it) also
holds a ref (run:…, experiment:…) or a citation ([@key p4]).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from louped import sources
from louped.core.paths import experiment_folder, experiments_dir
from louped.core.refs import parse
from louped.stores import trace
from louped.stores.runs import NotFound

#: A citation, as the app renders one: [@key] or [@key p4]. Anything else in [@…] is malformed.
CITE = re.compile(r"\[@([a-z0-9][a-z0-9-]{0,63})(?: p(\d+))?\]")
LOOSE = re.compile(r"\[@[^\]\s][^\]]*\]")
REF = re.compile(r"(?<![\w-])(?:run|experiment):[^\s`'\"()<>\[\],;]+")
#: A result number, signed or not, with thousands separators; not a part of a name (Llama-3.1-8B,
#: v0.2), a path, a URL or a longer number.
NUMBER = re.compile(r"(?<![\w./:#@,])(?<!\w-)[-\u2212+]?(?:\d+/\d+|(?:\d{1,3}(?:,\d{3})+|\d+)"
                    r"(?:\.\d+%?|%)|\d{1,3}(?:,\d{3})+)(?![\w%/]|[.,]\d|-[A-Za-z])")  # fmt: skip
CODE = re.compile(r"`[^`]*`")
COMMENT = re.compile(r"<!--.*?-->", re.S)
#: The folders checked when no path is given.
FOLDERS = ("experiments", "reports")


class Issue(BaseModel):
    #: Relative to the project.
    file: str
    line: int
    kind: Literal["number", "citation", "ref", "pin"]
    message: str


def check(paths: list[Path] | None = None) -> list[Issue]:
    """The issues in the given Markdown files and folders (every .md under experiments/ and
    reports/ when none), then in sources/pins.jsonl."""
    project = experiments_dir().parent
    files: list[Path] = []
    for path in paths or [project / f for f in FOLDERS]:
        if path.is_dir():
            files += sorted(path.rglob("*.md"))
        elif path.is_file():
            files.append(path)
        elif paths:
            raise FileNotFoundError(f"no file or folder {path}")
    for f in files:
        if not f.resolve().is_relative_to(project.resolve()):
            raise ValueError(f"{f} is not in the project ({project})")
    issues: list[Issue] = []
    found = {s.key: s for s in sources.list_sources()}
    pinned = {(p.key, p.page) for p in sources.pins()}
    for f in files:
        name = f.resolve().relative_to(project.resolve()).as_posix()
        for unit in _units(f.read_text(encoding="utf-8")):
            issues += _check_unit(name, unit, found, pinned)
    return issues + _stale_pins(found)


def _units(text: str) -> list[list[tuple[int, str]]]:
    """A Markdown file as the units a number's source must share, each a list of (line number,
    line): a paragraph, a list item, and a table with the paragraph just above it (its caption).
    A list item keeps its indented paragraphs. Code, headings, comments and front matter are left
    out."""
    units: list[list[tuple[int, str]]] = []
    lines = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text).splitlines()
    fence = None
    gap = "hard"  # what lies between the last unit and this line: none, blank lines, or a break
    paragraph = False  # whether the last unit is a paragraph, which a table can belong to
    listed = False  # whether the last unit is a list item, which keeps its indented lines
    start = 0
    if lines and lines[0].strip() == "---":
        start = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    for i, raw in enumerate(lines[start:], start + 1):
        s = raw.strip()
        found = re.match(r"(`{3,}|~{3,})(.*)", s)
        marker, rest = found.groups() if found else ("", "")
        if fence:
            # closed by a run of the same mark, at least as long, with nothing after it
            if marker[:1] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                fence = None
            continue
        if marker:
            fence, gap = marker, "hard"
            continue
        if s.startswith("#"):
            gap = "hard"
            continue
        if not s:
            gap = "blank" if gap == "none" else gap
            continue
        indented = raw.startswith((" ", "\t"))
        code = raw.startswith(("    ", "\t"))
        if code and gap != "none" and not (listed and gap == "blank"):
            gap = "hard"  # indented code
            continue
        item = re.match(r"([-*+]|\d+[.)])\s", s) is not None
        table = s.startswith("|")
        in_table = bool(units) and units[-1][-1][1].strip().startswith("|")
        caption = gap == "blank" and paragraph and not in_table
        joins = gap == "none" and not item and (in_table or not table)
        kept = listed and gap == "blank" and indented
        if units and (joins or kept or (table and (gap == "none" or caption))):
            units[-1].append((i, raw))
        else:
            units.append([(i, raw)])
            paragraph, listed = not item and not table, item
        gap = "none"
    return units


def _check_unit(name: str, unit: list[tuple[int, str]], found: dict[str, sources.Source],
                pinned: set[tuple[str, int]]) -> list[Issue]:  # fmt: skip
    issues: list[Issue] = []
    whole = "\n".join(raw for _, raw in unit)
    cites = list(CITE.finditer(whole))
    for m in LOOSE.finditer(whole):
        if not CITE.fullmatch(m.group(0)):
            why = f"{m.group(0)} is not a citation: write [@<key> p<page>], key in sources/"
            issues.append(Issue(file=name, line=unit[whole.count("\n", 0, m.start())][0],
                                kind="citation", message=why))  # fmt: skip
    refs = [(m.group(0).rstrip(".:"), m.start()) for m in REF.finditer(whole)]
    at = lambda pos: unit[whole.count("\n", 0, pos)][0]  # noqa: E731
    for m in cites:
        key, page = m.group(1), m.group(2)
        if key not in found:
            issues.append(Issue(file=name, line=at(m.start()), kind="citation",
                                message=f"{m.group(0)} names no source in sources/"))  # fmt: skip
        elif page is None:
            why = f"{m.group(0)} names no page: cite [@{key} p<page>]"
            issues.append(Issue(file=name, line=at(m.start()), kind="citation", message=why))
        elif not 1 <= int(page) <= found[key].pages:
            why = f"{m.group(0)}: {key} has pages 1 to {found[key].pages}"
            issues.append(Issue(file=name, line=at(m.start()), kind="citation", message=why))
        elif (key, int(page)) not in pinned:
            issues.append(Issue(file=name, line=at(m.start()), kind="citation",
                                message=f"{m.group(0)}: nothing is pinned on that page; pin the "
                                        "passage the claim rests on"))  # fmt: skip
    for ref, pos in refs:
        if why := _unresolved(ref):
            issues.append(Issue(file=name, line=at(pos), kind="ref",
                                message=f"{ref} does not resolve: {why}"))  # fmt: skip
    if not cites and not refs:
        for m in NUMBER.finditer(CODE.sub(lambda c: " " * len(c.group(0)), whole)):
            issues.append(Issue(file=name, line=at(m.start()), kind="number",
                                message=f"{m.group(0)} has no source beside it: add the ref of "
                                        "the run or file it came from, or a citation"))  # fmt: skip
    return issues


def _unresolved(ref: str) -> str | None:
    """Why a ref does not resolve; None when it does."""
    try:
        at = parse(ref)
        if at.scheme == "experiment" and at.path is None:
            experiment_folder(at.name)
        else:
            trace(ref)
    except (ValueError, KeyError, NotFound, FileNotFoundError) as exc:
        return str(exc.args[0]) if exc.args else type(exc).__name__
    return None


def _stale_pins(found: dict[str, sources.Source]) -> list[Issue]:
    """Pins whose source is gone, or whose quote is no longer on its page."""
    issues: list[Issue] = []
    texts: dict[tuple[str, int], str] = {}
    path = sources.sources_dir() / sources.PINS
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    numbers = [n for n, line in enumerate(lines, 1) if line.strip()]  # as pins() reads them
    for n, p in zip(numbers, sources.pins(), strict=True):
        if p.key not in found:
            why = f"pin {p.id} is on {p.key}, which is not in sources/ any more"
        else:
            try:
                if (p.key, p.page) not in texts:
                    texts[p.key, p.page] = sources.page_text(p.key, p.page)
                text = texts[p.key, p.page]
            except ValueError as exc:
                why = f"pin {p.id}: {exc}"
            else:
                if sources.find_quote(text, p.exact) is not None:
                    continue
                why = f"pin {p.id}: {p.exact[:60]!r} is no longer on page {p.page} of {p.key}"
        issues.append(Issue(file=f"sources/{sources.PINS}", line=n, kind="pin", message=why))
    return issues
