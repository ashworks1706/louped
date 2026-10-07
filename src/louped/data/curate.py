"""The curation ledger: one human decision per example, kept in source control.

An export can be run again and produces the same examples; the judgments about them cannot be
reproduced, so they live in a file of their own rather than inside the dataset. Each decision
carries the fingerprint of what was judged, so an example that changed underneath is reported
rather than trained on under a judgment about something else.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from louped.data.example import VERDICTS, Decision, Example, Verdict, fingerprint


class Ledger(BaseModel):
    """Every decision, by example id. The last decision about an example wins."""

    decisions: dict[str, Decision] = Field(default_factory=dict)

    def get(self, example_id: str) -> Decision | None:
        """The decision about one example, or None when it has none."""
        return self.decisions.get(example_id)

    def record(self, decision: Decision) -> None:
        """Add a decision, replacing any earlier one about the same example."""
        self.decisions[decision.id] = decision

    def counts(self) -> dict[str, int]:
        """How many decisions of each verdict."""
        return {v: sum(1 for d in self.decisions.values() if d.verdict == v) for v in VERDICTS}


def load(path: Path) -> Ledger:
    """The ledger at a path. A missing file is an empty ledger."""
    ledger = Ledger()
    if not path.exists():
        return ledger
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ledger.record(Decision.model_validate_json(line))
    return ledger


def save(path: Path, ledger: Ledger) -> None:
    """Write the ledger, one decision per line, sorted by example id so a diff reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (ledger.decisions[key].model_dump_json() for key in sorted(ledger.decisions))
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def pending(examples: Iterable[Example], ledger: Ledger) -> list[Example]:
    """Every example with no decision, and every example whose decision is stale."""
    waiting = []
    for example in examples:
        decision = ledger.get(example.id)
        if decision is None or decision.fingerprint != fingerprint(example):
            waiting.append(example)
    return waiting


def decide(example: Example, verdict: Verdict, reason: str, by: str) -> Decision:
    """A decision about an example, fingerprinted as it stands."""
    return Decision(
        id=example.id,
        verdict=verdict,
        reason=reason,
        fingerprint=fingerprint(example),
        by=by,
    )


def apply(examples: Sequence[Example], ledger: Ledger) -> tuple[list[Example], dict[str, int]]:
    """The accepted examples with fixed replies applied, and a count of the rest.

    An example with no decision is not training data, and neither is one whose decision is stale.
    Each accepted example's meta gets review ("kept by ana", "fixed by ana"): how its reply was
    picked, which the Training sets page shows (louped.data.pairs.sft_label).
    """
    accepted: list[Example] = []
    counts = {"kept": 0, "fixed": 0, "dropped": 0, "unreviewed": 0, "stale": 0}
    for example in examples:
        decision = ledger.get(example.id)
        if decision is None:
            counts["unreviewed"] += 1
            continue
        if decision.fingerprint != fingerprint(example):
            counts["stale"] += 1
            continue
        if decision.verdict == "drop":
            counts["dropped"] += 1
            continue
        if decision.verdict == "fix":
            if decision.reply is None:
                raise ValueError(f"{example.id}: a fix decision without the fixed reply")
            meta = {**example.meta, "review": f"fixed by {decision.by}"}
            accepted.append(example.model_copy(update={"reply": decision.reply, "meta": meta}))
            counts["fixed"] += 1
            continue
        meta = {**example.meta, "review": f"kept by {decision.by}"}
        accepted.append(example.model_copy(update={"meta": meta}))
        counts["kept"] += 1
    return accepted, counts
