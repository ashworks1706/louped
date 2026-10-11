"""Every eval task Launch can run: the project's own Inspect tasks, the benchmarks it makes from
Hub datasets, then inspect_evals' benchmarks.

The project's are the @task functions in experiments/<name>/*.py, found by reading the files
(nothing runs). Its Hub benchmarks are louped.toml's [benchmarks.<name>] tables, each the task
louped/<name> (louped.core.benchmarks). inspect_evals' come from the eval.yaml each benchmark
ships (title, group, what it measures, samples per task), read from the installed package
without importing it.
"""

from __future__ import annotations

import ast
import importlib.util
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from louped.core import experiments_dir
from louped.core.benchmarks import benchmarks, task_name


class EvalTask(BaseModel):
    #: What `inspect eval` takes: experiments/<name>/task.py@fn, louped/<name> or
    #: inspect_evals/<name>.
    task: str
    title: str
    group: str
    about: str | None = None
    samples: int | None = None
    source: Literal["project", "benchmark", "inspect_evals"]


def eval_tasks() -> list[EvalTask]:
    return [*project_tasks(), *benchmark_tasks(), *inspect_evals_tasks()]


def benchmark_tasks() -> list[EvalTask]:
    """The benchmarks louped.toml makes from Hub datasets ([benchmarks.<name>])."""
    out: list[EvalTask] = []
    for name, b in benchmarks().items():
        rows = f"{b.dataset}{f' ({b.config})' if b.config else ''}, {b.split}"
        about = f"{rows}: {b.input} to {b.target}, scored by {b.scorer}."
        out.append(EvalTask(task=task_name(name), title=name, group="Hub benchmarks",
                            about=about, source="benchmark"))  # fmt: skip
    return out


def project_tasks() -> list[EvalTask]:
    """The @task functions in the experiments' Python files."""
    root = experiments_dir()
    out: list[EvalTask] = []
    for path in sorted(root.glob("*/*.py")) if root.is_dir() else []:
        rel = path.relative_to(root.parent).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            if "@task" not in text:
                continue
            tree = ast.parse(text, filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(f"{rel} does not read as Python: {exc}") from exc
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and any(_is_task(d) for d in node.decorator_list):
                out.append(EvalTask(task=f"{rel}@{node.name}", title=node.name,
                                    group=path.parent.name, about=ast.get_docstring(node),
                                    source="project"))  # fmt: skip
    return out


def _is_task(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (isinstance(target, ast.Name) and target.id == "task") or (
        isinstance(target, ast.Attribute) and target.attr == "task"
    )


@cache
def inspect_evals_tasks() -> list[EvalTask]:
    """inspect_evals' benchmarks, one entry a task; empty when the package is not installed."""
    spec = importlib.util.find_spec("inspect_evals")
    if spec is None or not spec.submodule_search_locations:
        return []
    root = Path(next(iter(spec.submodule_search_locations)))
    out: list[EvalTask] = []
    for meta in sorted(root.glob("*/eval.yaml")):
        try:
            found = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
            tasks = [t for t in found.get("tasks") or [] if t["name"]]
        except (yaml.YAMLError, UnicodeDecodeError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"inspect_evals' {meta.parent.name}/eval.yaml: {exc!r}") from exc
        about = (found.get("description") or "").strip() or None
        for t in tasks:
            out.append(EvalTask(task=f"inspect_evals/{t['name']}",
                                title=found.get("title") or t["name"],
                                group=found.get("group") or "Other", about=about,
                                samples=t.get("dataset_samples"),
                                source="inspect_evals"))  # fmt: skip
    return out
