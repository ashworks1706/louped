"""Labels the researcher gives each item by hand, kept per run in labels/<run>.json here."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
SAVED = Path(__file__).parent / "labels"
CHOICES = ["letter", "agreement", "unclear"]
RUN = re.compile(r"^[A-Za-z0-9-]+$")


class Label(BaseModel):
    label: str | None


def saved(run: str) -> Path:
    if not RUN.match(run):
        raise HTTPException(400, f"not a run id: {run}")
    return SAVED / f"{run}.json"


def read(run: str) -> dict[str, str]:
    path = saved(run)
    return json.loads(path.read_text()) if path.is_file() else {}


@router.get("/{run}")
def labels(run: str) -> dict:
    return {"choices": CHOICES, "labels": read(run)}


@router.put("/{run}/{qid}")
def label(run: str, qid: str, body: Label) -> dict[str, str]:
    if body.label is not None and body.label not in CHOICES:
        raise HTTPException(400, f"a label is one of {', '.join(CHOICES)}")
    found = read(run)
    if body.label is None:
        found.pop(qid, None)
    else:
        found[qid] = body.label
    SAVED.mkdir(exist_ok=True)
    saved(run).write_text(json.dumps(found, indent=2))
    return found
