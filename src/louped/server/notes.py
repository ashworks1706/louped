"""Notes on any part of the app's pages (louped.stores.notes): read anywhere, written only where
the app launches."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from louped.server.launch import require_json
from louped.stores import notes as store
from louped.stores.notes import Note, NoteDraft


class NoteText(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


def router(editing: Callable[[], None]) -> APIRouter:
    api = APIRouter(prefix="/api/notes")

    def found(id: str) -> Note:
        try:
            return store.get(id)
        except KeyError as exc:
            raise HTTPException(404, f"no note {id}") from exc

    @api.get("")
    def notes(
        run: str | None = None, experiment: str | None = None, part: str | None = None
    ) -> list[Note]:
        """Every note, newest first; with run, experiment or part (an address, or the start of
        one), those with a part there."""
        return store.list_notes(run, experiment, part)

    @api.get("/{id}")
    def note(id: str) -> Note:
        return found(id)

    @api.post("", dependencies=[Depends(require_json)])
    def add(req: NoteDraft) -> Note:
        editing()
        try:
            return store.create(req)
        except ValueError as exc:
            raise HTTPException(413, str(exc)) from exc

    @api.put("/{id}", dependencies=[Depends(require_json)])
    def edit(id: str, req: NoteText) -> Note:
        """Changes what a note says; the parts it is on stay."""
        editing()
        found(id)
        return store.edit(id, req.text)

    @api.delete("/{id}")
    def delete(id: str) -> None:
        """Moves it to the trash (<home>/trash/notes)."""
        editing()
        found(id)
        store.delete(id)

    return api
