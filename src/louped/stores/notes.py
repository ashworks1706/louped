"""Notes on any part of the app's pages, as a PDF reader's notes are on a page.

A note is Markdown on one or more parts, each named by its address (louped.server.parts) and the
page it was written on, with the text the part showed and the data it stood for then: a note
still reads right when the part changes or goes. A note on a figure can hold the points a person
drew a lasso around, with their item ids. The person writes notes in the app (Shift+click parts,
then Note); an agent writes them with add_note.

Notes are the project's, one file each under notes/<id>.json at its root, so they go into git
with the experiments and two people's notes do not touch the same file.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, field_validator

from louped.core.paths import trash
from louped.core.project import base

#: A part's address, as louped.server.parts.ADDRESS reads one.
ADDRESS = re.compile(r"^[a-z.]+(/[^\s/]+)*$")

#: A note's anchors' data together: the points of a lasso, a row's record. More is refused.
MAX_DATA = 200_000


class Anchor(BaseModel):
    """A part a note is on, where, and what it showed when the note was written."""

    part: str = Field(max_length=300)
    #: The page's path and query, as the app showed it.
    url: str = Field(min_length=1, max_length=2000)
    run: str | None = None
    experiment: str | None = None
    #: The part's text then.
    shows: str = Field("", max_length=500)
    #: What the part stood for then: an item's record, a figure's lassoed points.
    data: JsonValue = None

    @field_validator("part")
    @classmethod
    def _address(cls, part: str) -> str:
        if not ADDRESS.match(part):
            raise ValueError(f"{part!r} is not a part's address")
        return part

    @field_validator("url")
    @classmethod
    def _path(cls, url: str) -> str:
        if not url.startswith("/") or url.startswith("//"):
            raise ValueError(f"{url!r} is not a page of the app: give its path, such as /runs/")
        return url


class NoteDraft(BaseModel):
    """What a note says, and on what."""

    text: str = Field(min_length=1, max_length=20_000)
    anchors: list[Anchor] = Field(min_length=1, max_length=50)
    #: Who wrote it.
    by: Literal["person", "agent"] = "person"


class Note(NoteDraft):
    id: str
    created: datetime
    updated: datetime


def notes_dir() -> Path:
    return base() / "notes"


def _path(id: str) -> Path:
    if not id.isalnum():
        raise KeyError(id)
    return notes_dir() / f"{id}.json"


def _check(draft: NoteDraft) -> None:
    size = len(json.dumps([a.data for a in draft.anchors]))
    if size > MAX_DATA:
        raise ValueError(f"the parts' data is {size} bytes, over {MAX_DATA}; note on fewer "
                         "parts or fewer points")  # fmt: skip


def _write(note: Note) -> Note:
    path = _path(note.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".json.part")
    part.write_text(note.model_dump_json(indent=2), encoding="utf-8")
    os.replace(part, path)
    return note


def list_notes(run: str | None = None, experiment: str | None = None,
               part: str | None = None) -> list[Note]:  # fmt: skip
    """Every note, newest first; with run, experiment or part, those with an anchor there (part
    by address, or by a prefix ending at a /)."""
    if not notes_dir().is_dir():
        return []
    found = [Note.model_validate_json(p.read_text(encoding="utf-8"))
             for p in notes_dir().glob("*.json")]  # fmt: skip

    def on(a: Anchor) -> bool:
        if run is not None and a.run != run:
            return False
        if experiment is not None and a.experiment != experiment:
            return False
        return part is None or a.part == part or a.part.startswith(part.rstrip("/") + "/")

    return sorted((n for n in found if any(on(a) for a in n.anchors)),
                  key=lambda n: n.created, reverse=True)  # fmt: skip


def get(id: str) -> Note:
    path = _path(id)
    if not path.is_file():
        raise KeyError(id)
    return Note.model_validate_json(path.read_text(encoding="utf-8"))


def create(draft: NoteDraft) -> Note:
    _check(draft)
    now = datetime.now(UTC)
    return _write(Note(**draft.model_dump(), id=secrets.token_hex(4), created=now, updated=now))


def edit(id: str, text: str) -> Note:
    """Change what a note says; its parts stay."""
    was = get(id)
    return _write(was.model_copy(update={"text": NoteDraft(text=text, anchors=was.anchors).text,
                                         "updated": datetime.now(UTC)}))  # fmt: skip


def delete(id: str) -> Path:
    """Move a note to the trash (<home>/trash/notes); returns where it went."""
    return trash(_path(get(id).id), "notes")
