"""Refs: one address for a piece of evidence, so a figure's mark (and later a claim or a
citation) can say where it comes from, and the app and the agent can follow it there.

    run:<run id>                        a run
    run:<run id>/<path>                 a file the run logged: its records, a derived file, a figure
    run:<run id>/<path>#<item>          one item of it: a record, a figure's mark
    experiment:<name>/<path>[#<item>]   an experiment's own file, such as one of its figures

The item is the records' key as text, as the Items tab writes it. louped.stores.trace follows a
ref down to the rows, scripts and commits behind it.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

Scheme = Literal["run", "experiment"]
_REF = re.compile(r"^(run|experiment):([^/#\s]+)(?:/([^#]+))?(?:#(.+))?$", re.S)
#: A ref where it stands in prose: up to a space, quote, bracket, brace or list punctuation.
#: Trailing . and : end the sentence, not the ref; strip them.
IN_TEXT = re.compile(r"(?<![\w-])(?:run|experiment):[^\s`'\"()<>\[\]{},;]+")


class Ref(BaseModel):
    scheme: Scheme
    #: The run id or experiment name.
    name: str
    #: A file under the run or the experiment's folder.
    path: str | None = None
    #: An item's key, as text.
    item: str | None = None

    def __str__(self) -> str:
        return ref(self.scheme, self.name, self.path, self.item)


def ref(scheme: Scheme, name: str, path: str | None = None, item: str | None = None) -> str:
    return f"{scheme}:{name}{f'/{path}' if path else ''}{f'#{item}' if item is not None else ''}"


def parse(text: str) -> Ref:
    """A ref from its text; ValueError naming the shape when it is not one."""
    m = _REF.match(text)
    if m is None:
        raise ValueError(f"{text!r} is not a ref: run:<run id>[/<path>][#<item>] or "
                         "experiment:<name>/<path>[#<item>]")  # fmt: skip
    scheme, name, path, item = m.groups()
    if path is not None and (path.startswith("/") or "\\" in path
                             or any(p in ("", ".", "..") for p in path.split("/"))):  # fmt: skip
        raise ValueError(f"{path!r} is not a path inside {scheme} {name}")
    return Ref.model_validate({"scheme": scheme, "name": name, "path": path, "item": item})
