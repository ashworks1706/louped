"""A run's items lined up across its conditions, and a cohort of them.

A folder of two to MAX_CONDITIONS JSONL files is one file per condition over the same items; the
Items tab reads a folder the same way (apps/web/src/lib/artifacts.ts: itemFolders, joinKey,
defaultField). On a cohort (a set of item ids) each condition gets its value with a Wilson
interval for a 0/1 field, and against the reference the paired difference over the items both
hold, with the same seeded bootstrap interval compare uses.
"""

from __future__ import annotations

import json
import math
import re

from pydantic import BaseModel, Field

from louped.stores.compare import interval
from louped.stores.runs import get_run, read_artifact
from louped.stores.types import PairedScore

MAX_CONDITIONS = 12
REFERENCE = re.compile(r"^(baseline|base|control|reference|original|unmitigated|before)$", re.I)
KEY_NAMES = ("id", "sample_id", "item_id", "qid", "uid", "key", "idx", "index", "question_id")
OUTCOME_NAMES = ("correct", "score", "pass", "passed", "accuracy", "acc", "label", "pred")

Row = dict[str, object]


class Condition(BaseModel):
    name: str
    #: Cohort items this condition's file holds.
    n: int
    #: For a numeric field: its mean on them; for a 0/1 field, the rate, with k of n and a 95%
    #: Wilson interval.
    mean: float | None
    k: int | None = None
    interval95: tuple[float, float] | None = None
    #: How many items have a different value from the reference.
    changed: int | None = None


class CohortStats(BaseModel):
    run: str
    folder: str
    key: str
    field: str
    reference: str
    #: Items asked for that no file holds.
    missing: list[str]
    #: Items asked for that some file holds (all of the run's when no ids were given).
    n: int
    conditions: list[Condition]
    #: Each other condition minus the reference, paired over the items both hold; for a 0/1
    #: field up is 0→1 and down 1→0.
    paired: list[PairedScore] = Field(default_factory=list)
    #: Why there is no paired difference, when there is none.
    unpaired: str | None = None


def _stem(path: str) -> str:
    return re.sub(r"\.(jsonl|ndjson)$", "", path.rsplit("/", 1)[-1], flags=re.I)


def folders(paths: list[str]) -> dict[str, list[str]]:
    """Folders of two to MAX_CONDITIONS JSONL files, each with a reference-like file first."""
    by: dict[str, list[str]] = {}
    for p in paths:
        if p.lower().endswith((".jsonl", ".ndjson")):
            by.setdefault(p.rsplit("/", 1)[0] if "/" in p else "", []).append(p)
    return {
        d: sorted(fs, key=lambda f: (not REFERENCE.match(_stem(f)), f.casefold(), f))
        for d, fs in sorted(by.items(), key=lambda kv: (kv[0].casefold(), kv[0]))
        if 2 <= len(fs) <= MAX_CONDITIONS
    }


def _rows(run_id: str, path: str) -> list[Row]:
    rows = []
    text = read_artifact(run_id, path).decode("utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} line {i} is not JSON: {e}") from e
        if not isinstance(row, dict):
            raise ValueError(f"{path} line {i} is not an object")
        rows.append(row)
    return rows


def join_key(tables: list[list[Row]]) -> str | None:
    """The field naming an item in every file: in every row, scalar and unique per file."""
    if not tables or any(not t for t in tables):
        return None

    def names_items(k: str) -> bool:
        for t in tables:
            seen = set()
            for r in t:
                v = r.get(k)
                if v is None or isinstance(v, bool | dict | list) or v in seen:
                    return False
                seen.add(v)
        return True

    found = [k for k in tables[0][0] if names_items(k)]
    return next((n for n in KEY_NAMES if n in found), found[0] if found else None)


def _text(v: object) -> str:
    """An item's id as text, as the app writes it (JavaScript's String): 3.0 is "3"."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _binary(v: object) -> int | None:
    if v is True or (v == 1 and not isinstance(v, bool | str)):
        return 1
    if v is False or (v == 0 and not isinstance(v, bool | str)):
        return 0
    return None


def _number(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) else None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def cohort(
    run_id: str,
    ids: list[str] | None = None,
    folder: str | None = None,
    field: str | None = None,
    reference: str | None = None,
) -> CohortStats:
    """Each condition on the items ids names (every item when None), and its paired difference
    from the reference. Unset, folder is the first by name, field a conventional outcome name
    (correct, score, ...) else the first 0/1 field, and reference a baseline-like file else the
    first by name: the Items tab's own defaults, not a layout's. A name that is not there is an
    error, not a default."""
    found = folders([a.path for a in get_run(run_id).artifacts])
    if not found:
        raise ValueError(f"run {run_id} has no folder of 2 to {MAX_CONDITIONS} JSONL files")
    if folder is None:
        folder = next(iter(found))
    if folder not in found:
        raise ValueError(f"no folder {folder!r} of conditions; there are {list(found)}")
    files = found[folder]
    names = [_stem(f) for f in files]
    tables = [_rows(run_id, f) for f in files]
    key = join_key(tables)
    if key is None:
        raise ValueError(f"the files in {folder!r} share no field naming an item once in each")
    fields = [
        f for f in tables[0][0]
        if f != key and all(f in t[0] and not isinstance(t[0][f], dict | list) for t in tables)
    ]  # fmt: skip
    binary_field = next(
        (f for f in fields if all(_binary(r.get(f)) is not None for t in tables for r in t)), None
    )
    if not fields:
        raise ValueError(f"the files in {folder!r} share no scalar field to compare on")
    if field is None:
        field = next((n for n in OUTCOME_NAMES if n in fields), binary_field or fields[0])
    if field not in fields:
        raise ValueError(f"no field {field!r} in every file; there are {fields}")
    if reference is None:
        reference = names[0]
    if reference not in names:
        raise ValueError(f"no condition {reference!r}; there are {names}")

    by = [{_text(r[key]): r for r in t} for t in tables]
    held = list(dict.fromkeys(i for b in by for i in b))
    wanted = held if ids is None else list(dict.fromkeys(ids))
    missing = [i for i in wanted if not any(i in b for b in by)]
    items = [i for i in wanted if any(i in b for b in by)]
    # read as 0/1 or as numbers by every item, as the Items tab does, so a cohort reads the same
    # way as the whole; a missing value (null) is left out, not a reason to stop
    present = [r[field] for t in tables for r in t if r.get(field) is not None]
    binary = all(_binary(v) is not None for v in present)
    numeric = all(_number(v) is not None for v in present)
    value = _binary if binary else _number
    unpaired = (
        None
        if binary or numeric
        else f"{field} is not a number on every item; the conditions are counted as changed"
    )

    ref = by[names.index(reference)]
    conditions: list[Condition] = []
    paired: list[PairedScore] = []
    for name, b in zip(names, by, strict=True):
        own = [i for i in items if i in b]
        vals = [value(b[i].get(field)) for i in own] if binary or numeric else []
        nums = [v for v in vals if v is not None]
        k = int(sum(nums)) if binary else None
        conditions.append(Condition(
            name=name, n=len(own), mean=sum(nums) / len(nums) if nums else None, k=k,
            interval95=wilson(k, len(nums)) if k is not None else None,
            changed=None if name == reference else sum(
                1 for i in own if i in ref and ref[i].get(field) != b[i].get(field)),
        ))  # fmt: skip
        if name == reference or not (binary or numeric):
            continue
        pairs = [
            (x, y)
            for i in own
            if i in ref
            and (x := value(ref[i].get(field))) is not None
            and (y := value(b[i].get(field))) is not None
        ]
        if not pairs:
            continue
        diffs = [y - x for x, y in pairs]
        low, high = interval(diffs)
        paired.append(PairedScore(
            name=name, n=len(pairs), mean_a=sum(x for x, _ in pairs) / len(pairs),
            mean_b=sum(y for _, y in pairs) / len(pairs), diff=sum(diffs) / len(diffs),
            low=low, high=high, up=sum(d > 0 for d in diffs), down=sum(d < 0 for d in diffs),
        ))  # fmt: skip
    return CohortStats(
        run=run_id, folder=folder, key=key, field=field, reference=reference, missing=missing,
        n=len(items), conditions=conditions, paired=paired, unpaired=unpaired,
    )  # fmt: skip
