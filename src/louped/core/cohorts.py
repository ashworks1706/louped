"""A cohort: items of a run a person picked (or an agent named), saved by name in the experiment
as experiments/<name>/cohorts/<cohort>.json, so a later run can be made on just them.

The file is the project's, to commit with the experiment: it says which items, from which run's
records, and why.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from louped.core.paths import NAME, experiment_folder, inside

#: A cohort's name: what its file is called and what --cohort takes.


class Cohort(BaseModel):
    """Items by id, and where they were picked."""

    #: The ids, as the records' key field holds them (as text).
    ids: list[str] = Field(min_length=1, max_length=100_000)
    #: The run whose records they were picked from, and the folder of those records.
    run: str | None = Field(None, max_length=300)
    folder: str = Field("", max_length=500)
    #: The field naming an item in every record, such as qid.
    key: str | None = Field(None, max_length=200)
    #: Why these items: what they have in common.
    note: str = Field("", max_length=4000)
    created: str = ""

    @field_validator("ids")
    @classmethod
    def _once(cls, ids: list[str]) -> list[str]:
        return list(dict.fromkeys(ids))


class Saved(Cohort):
    name: str


def _path(experiment: str, name: str) -> Path:
    if not NAME.match(name):
        raise ValueError(f"{name!r} is not a cohort name: lowercase letters, digits and -")
    return inside(experiment_folder(experiment), "cohorts", f"{name}.json")


def read(experiment: str, name: str) -> Saved:
    """A saved cohort; FileNotFoundError naming the file when there is none."""
    path = _path(experiment, name)
    if not path.is_file():
        raise FileNotFoundError(f"no cohort {name!r}: {path} does not exist")
    try:
        cohort = Cohort.model_validate_json(path.read_text("utf-8"))
    except ValidationError as e:
        raise ValueError(f"{path} is not a cohort: {e}") from e
    return Saved(name=name, **cohort.model_dump())


def listed(experiment: str) -> list[Saved]:
    """An experiment's saved cohorts, by name."""
    folder = experiment_folder(experiment) / "cohorts"
    if not folder.is_dir():
        return []
    files = sorted(folder.glob("*.json"))
    if bad := [p.name for p in files if not NAME.match(p.stem)]:
        raise ValueError(f"not cohort names (lowercase letters, digits and -): {', '.join(bad)}")
    return [read(experiment, p.stem) for p in files]


def save(experiment: str, name: str, cohort: Cohort) -> Saved:
    """Writes a cohort, replacing one of the same name."""
    path = _path(experiment, name)
    path.parent.mkdir(exist_ok=True)
    cohort = cohort.model_copy(update={"created": cohort.created or f"{datetime.now(UTC):%FT%TZ}"})
    path.write_text(cohort.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return Saved(name=name, **cohort.model_dump())
