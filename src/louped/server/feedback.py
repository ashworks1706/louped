"""Feature requests and bug reports for louped, on the Feedback page (louped.stores.feedback)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from louped.server.launch import require_json
from louped.stores import feedback as store
from louped.stores.feedback import FORMS, Draft, Feedback


class Field(BaseModel):
    id: str
    label: str


class Form(BaseModel):
    """A kind's issue form on GitHub (.github/ISSUE_TEMPLATE) and its fields, in order."""

    kind: store.Kind
    template: str
    fields: list[Field]


def router(editing: Callable[[], None]) -> APIRouter:
    api = APIRouter(prefix="/api/feedback")

    def found(id: str) -> Feedback:
        try:
            return store.get(id)
        except KeyError as exc:
            raise HTTPException(404, f"no request {id}") from exc

    @api.get("")
    def feedback() -> list[Feedback]:
        """Every request, newest first: drafts and those opened on GitHub. Off on a shared
        server: a bug's steps can name this machine's paths."""
        editing()
        return store.list_feedback()

    @api.get("/forms")
    def forms() -> list[Form]:
        """Each kind's form: what a feature request or a bug report asks."""
        return [Form(kind=kind, template=template,  # type: ignore[arg-type]
                     fields=[Field(id=k, label=v) for k, v in fields.items()])
                for kind, (template, fields) in FORMS.items()]  # fmt: skip

    @api.post("", dependencies=[Depends(require_json)])
    def draft(req: Draft) -> Feedback:
        """Keeps a draft for the person to read on the Feedback page; nothing goes to GitHub."""
        editing()
        try:
            return store.create(req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.put("/{id}", dependencies=[Depends(require_json)])
    def edit(id: str, req: Draft) -> Feedback:
        editing()
        found(id)
        try:
            return store.update(id, req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/{id}/opened", dependencies=[Depends(require_json)])
    def opened(id: str) -> Feedback:
        """Marks that the person opened it on GitHub to submit it."""
        editing()
        found(id)
        return store.mark_opened(id)

    @api.delete("/{id}")
    def delete(id: str) -> None:
        """Moves it to the trash (<home>/trash/feedback)."""
        editing()
        found(id)
        store.delete(id)

    return api
