"""Judges: how a model picks the better of two answers, one file each in the project's judges/.

A judge is judges/<name>.py, committed with the project:

    '''Which answer admits what it does not know?'''   # what it is for, on Compare and Launch
    CRITERION = "Which answer is more honest about its uncertainty?"
    PROMPT = "..."   # optional: {request}, {first}, {second} and {criterion}; ends in a verdict
    MODEL = "louped/Qwen/Qwen2.5-7B-Instruct"   # optional: the judge model it is meant for

    def verdict(reply: str) -> str | None:   # optional: "1", "2", "tie" or None
        ...

Listing reads the file without running it (its constants and whether it has verdict), so the
app shows judges whether launching is on or not; only a judging job imports it. "default" is
louped's own judge and needs no file.
"""

from __future__ import annotations

import ast
import importlib.util
import string
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from louped.core.paths import NAME, experiments_dir, inside

CRITERION = "Which answer is more correct and more helpful?"

PROMPT = """Compare two answers to the same request.

[Request]
{request}

[Answer 1]
{first}

[Answer 2]
{second}

{criterion} Think briefly, then end with one line: "Verdict: 1", "Verdict: 2" or "Verdict: tie"."""

#: The model a judge runs on when neither it nor the launch names one.
MODEL = "louped/Qwen/Qwen2.5-1.5B-Instruct"
#: The fields a prompt must fill: the request and both answers.
FIELDS = {"request", "first", "second"}


class Judge(BaseModel):
    name: str
    #: What it is for, from the file's docstring.
    about: str | None = None
    criterion: str
    prompt: str = PROMPT
    model: str = MODEL
    #: Its own verdict(reply) reads the replies; else louped's "Verdict: 1|2|tie" line.
    parses: bool = False
    #: judges/<name>.py, or None for louped's own.
    path: str | None = None


DEFAULT = Judge(name="default", about="louped's own: correct and helpful.", criterion=CRITERION)


def project_dir() -> Path:
    """The project's root, where experiments/ and judges/ sit."""
    return experiments_dir().parent


def judges_dir() -> Path:
    return project_dir() / "judges"


def find_judges() -> list[Judge]:
    """louped's judge, then the project's by name. A file that is not a judge is an error naming
    it, not a judge that silently goes missing."""
    root = judges_dir()
    files = sorted(root.glob("*.py")) if root.is_dir() else []
    return [DEFAULT, *(_read(f) for f in files if not f.name.startswith("_"))]


def judge_named(name: str) -> Judge:
    """One judge by name; FileNotFoundError when the project has none of that name."""
    if name == DEFAULT.name:
        return DEFAULT
    path = _file(name)
    if not path.is_file():
        raise FileNotFoundError(f"no judge {name!r}: judges/{name}.py")
    return _read(path)


def write_judge(name: str, criterion: str, prompt: str | None = None, model: str | None = None,
                about: str | None = None) -> Judge:  # fmt: skip
    """Write judges/<name>.py (replacing one of that name) and return it as read back. A file
    with code of its own (a verdict function) is the person's to edit, so it is refused."""
    if name == DEFAULT.name:
        raise ValueError("default is louped's own judge: name yours something else")
    if prompt is not None:
        _check_prompt(prompt)
    path = _file(name)
    if path.is_file() and (own := _own_code(path)):
        raise ValueError(f"judges/{name}.py has code of its own ({', '.join(own)}): edit the "
                         "file instead of replacing it")  # fmt: skip
    lines = [repr(about or criterion), "", f"CRITERION = {criterion!r}"]
    if prompt is not None:
        lines.append(f"PROMPT = {prompt!r}")
    if model is not None:
        lines.append(f"MODEL = {model!r}")
    text = "\n".join(lines) + "\n"
    ast.parse(text)  # what is written always reads back
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return _read(path)


def load_verdict(judge: Judge) -> Callable[[str], str | None] | None:
    """The judge's own verdict(reply), imported from its file; None when it has none."""
    if not judge.parses or judge.path is None:
        return None
    path = project_dir() / judge.path
    spec = importlib.util.spec_from_file_location(f"louped_judge_{judge.name}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{path} is not a Python file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verdict


#: What write_judge writes; anything else in a judge's file is the person's own code.
_WRITTEN = {"CRITERION", "PROMPT", "MODEL"}


def _own_code(path: Path) -> list[str]:
    """The top-level statements of a judge's file that write_judge would not write back."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return ["a file that does not parse"]
    own: list[str] = []
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # the docstring
        if isinstance(node, ast.Assign) and _binds(node) <= _WRITTEN and len(node.targets) == 1:
            continue
        own.append(getattr(node, "name", None) or type(node).__name__.lower())
    return own


def _file(name: str) -> Path:
    if not NAME.match(name):
        raise ValueError(f"{name!r} is not a judge name: lowercase letters, digits and -")
    return inside(judges_dir(), f"{name}.py")


def _read(path: Path) -> Judge:
    """A judge from its file's constants, without running it."""
    root = project_dir()
    where = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    if not NAME.match(path.stem):
        raise ValueError(f"{where}: a judge's file name is lowercase letters, digits and -")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ValueError(f"{where}: {exc}") from exc
    found: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"CRITERION", "PROMPT", "MODEL"}):  # fmt: skip
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                raise ValueError(f"{where}: {node.targets[0].id} is a plain string")
            found[node.targets[0].id] = node.value.value
    if "CRITERION" not in found:
        raise ValueError(f"{where}: a judge sets CRITERION, the question it answers for a pair")
    if "PROMPT" in found:
        try:
            _check_prompt(found["PROMPT"])
        except ValueError as exc:
            raise ValueError(f"{where}: {exc}") from exc
    parses = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "verdict":
            parses = True
        elif "verdict" in _binds(node):
            raise ValueError(f"{where}: verdict is a plain def verdict(reply) in the file, so "
                             "the list can see it without running the file")  # fmt: skip
    return Judge(name=path.stem, about=ast.get_docstring(tree), criterion=found["CRITERION"],
                 prompt=found.get("PROMPT", PROMPT), model=found.get("MODEL", MODEL),
                 parses=parses, path=where)  # fmt: skip


def _binds(node: ast.stmt) -> set[str]:
    """The names a top-level statement other than a plain def binds."""
    if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef):
        return {node.name}
    if isinstance(node, ast.Import | ast.ImportFrom):
        return {(a.asname or a.name).split(".")[0] for a in node.names}
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign | ast.AugAssign):
        targets = [node.target]
    else:
        targets = []
    return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}


def _check_prompt(prompt: str) -> None:
    try:
        named = {f for _, f, _, _ in string.Formatter().parse(prompt) if f is not None}
    except ValueError as exc:
        raise ValueError(f"PROMPT is not a template: {exc}") from exc
    if missing := FIELDS - named:
        raise ValueError(f"PROMPT leaves out {', '.join(sorted(missing))}: it fills "
                         "{request}, {first}, {second} and {criterion}")  # fmt: skip
    if extra := named - FIELDS - {"criterion"}:
        raise ValueError(f"PROMPT has fields it cannot fill: {', '.join(sorted(extra))}")
