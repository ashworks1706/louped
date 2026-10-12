"""Feature requests and bug reports for louped itself, drafted here and filed on GitHub.

An agent (or the person) drafts one; it is kept under <home>/feedback/<id>.json until the person
reads it on the Feedback page and opens it on GitHub. Filing goes through GitHub's own new-issue
page, prefilled from the repository's issue forms (.github/ISSUE_TEMPLATE), so louped holds no
GitHub token and nothing is sent until the person submits it there.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, Field, computed_field

from louped import __version__
from louped.core.paths import home, trash

#: Where louped's issues are filed.
NEW_ISSUE = "https://github.com/ashworks1706/louped/issues/new"
#: The longest prefilled link GitHub opens; a longer one is refused (414).
MAX_URL = 8000

Kind = Literal["feature", "bug"]

#: Each kind's issue form and its fields, by the form's ids, with the form's labels.
FORMS: dict[str, tuple[str, dict[str, str]]] = {
    "feature": ("feature.yml", {"problem": "The research task it enables",
                                "prebuilt": "Existing tools that already do part of it"}),
    "bug": ("bug.yml", {"what": "What happened, and what you expected",
                        "repro": "Steps to reproduce"}),
}  # fmt: skip


class Draft(BaseModel):
    """What a request says: its kind, a title and its form's fields."""

    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    #: The form's fields by id (feature: problem, prebuilt; bug: what, repro).
    fields: dict[str, str] = {}


class Feedback(Draft):
    id: str
    created: datetime
    #: When the person opened it on GitHub to submit it; None while it is a draft.
    opened: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def issue_url(self) -> str:
        """GitHub's new-issue page with this request filled into its form. The louped version is
        added to the last field."""
        template, fields = FORMS[self.kind]
        values = {k: self.fields.get(k, "").strip() for k in fields}
        last = list(fields)[-1]
        values[last] = f"{values[last]}\n\nlouped {__version__}".strip()
        return f"{NEW_ISSUE}?{urlencode({'template': template, 'title': self.title, **values})}"


def _dir() -> Path:
    return home() / "feedback"


def _path(id: str) -> Path:
    if not id.isalnum():
        raise KeyError(id)
    return _dir() / f"{id}.json"


def _check(draft: Draft) -> None:
    if extra := sorted(set(draft.fields) - set(FORMS[draft.kind][1])):
        raise ValueError(f"a {draft.kind} has no field {', '.join(extra)}; it has "
                         f"{', '.join(FORMS[draft.kind][1])}")  # fmt: skip
    probe = Feedback(**draft.model_dump(), id="x", created=datetime.now(UTC))
    if (size := len(probe.issue_url)) > MAX_URL:
        raise ValueError(f"too long for GitHub's prefilled link: {size} characters encoded, "
                         f"at most {MAX_URL}; shorten it")  # fmt: skip


def _write(item: Feedback) -> Feedback:
    path = _path(item.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".json.part")
    part.write_text(item.model_dump_json(exclude={"issue_url"}, indent=2), encoding="utf-8")
    os.replace(part, path)
    return item


def list_feedback() -> list[Feedback]:
    """Every request, newest first."""
    if not _dir().is_dir():
        return []
    items = [Feedback.model_validate(json.loads(p.read_text(encoding="utf-8")))
             for p in _dir().glob("*.json")]  # fmt: skip
    return sorted(items, key=lambda f: f.created, reverse=True)


def get(id: str) -> Feedback:
    path = _path(id)
    if not path.is_file():
        raise KeyError(id)
    return Feedback.model_validate(json.loads(path.read_text(encoding="utf-8")))


def create(draft: Draft) -> Feedback:
    _check(draft)
    item = Feedback(**draft.model_dump(), id=secrets.token_hex(4), created=datetime.now(UTC))
    return _write(item)


def update(id: str, draft: Draft) -> Feedback:
    _check(draft)
    was = get(id)
    return _write(was.model_copy(update=draft.model_dump()))


def mark_opened(id: str) -> Feedback:
    return _write(get(id).model_copy(update={"opened": datetime.now(UTC)}))


def delete(id: str) -> None:
    trash(_path(get(id).id), "feedback")
