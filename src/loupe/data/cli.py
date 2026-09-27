"""`loupe data ...`: the steps from a product's traces to a reviewed training set.

Every step reads and writes under <home>/data/<name>/ unless given paths:
raw.jsonl (export) -> verified.jsonl (verify) -> sft.jsonl (curate). The review ledger is
experiments/<name>/decisions.jsonl, in source control, because judgments cannot be regenerated.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import tyro

from loupe.core import experiments_dir, home
from loupe.data import curate, read_jsonl, redact, sources, verify, write_jsonl


def _dir(name: str) -> Path:
    return home() / "data" / name


def _ledger(name: str, given: Path | None) -> Path:
    return given or experiments_dir() / name / "decisions.jsonl"


@dataclass(frozen=True)
class Export:
    """Read a product's model calls, redact them, write raw.jsonl."""

    name: str
    """The dataset; also the experiments/ folder its ledger lives in."""
    source: Literal["traces", "phoenix"]
    path: Path | None = None
    """traces: the directory of <org>/<request>.jsonl trace files."""
    url: str = "http://127.0.0.1:6006"
    """phoenix: the self-hosted Phoenix base URL."""
    project: str = "default"
    """phoenix: the project the spans are under."""
    days: int = 0
    """traces: skip files older than this; 0 reads every one."""
    redact_extra: tuple[str, ...] = ()
    """Extra redaction patterns by name, e.g. asu-id."""
    out: Path | None = None


@dataclass(frozen=True)
class Verify:
    """Drop malformed examples and duplicates; write verified.jsonl."""

    name: str
    src: Path | None = None
    out: Path | None = None


@dataclass(frozen=True)
class Review:
    """Judge each unreviewed example in the terminal: keep, drop, fix its reply, or skip."""

    name: str
    src: Path | None = None
    ledger: Path | None = None
    by: str = ""
    limit: int = 0


@dataclass(frozen=True)
class Curate:
    """Build sft.jsonl from the examples a reviewer accepted."""

    name: str
    src: Path | None = None
    ledger: Path | None = None
    out: Path | None = None


@dataclass(frozen=True)
class Stats:
    """What the training set holds and how much is still unreviewed."""

    name: str


Command = (
    Annotated[Export, tyro.conf.subcommand("export")]
    | Annotated[Verify, tyro.conf.subcommand("verify")]
    | Annotated[Review, tyro.conf.subcommand("review")]
    | Annotated[Curate, tyro.conf.subcommand("curate")]
    | Annotated[Stats, tyro.conf.subcommand("stats")]
)


def run(cmd: Command) -> None:
    match cmd:
        case Export():
            if cmd.source == "traces":
                if cmd.path is None:
                    raise SystemExit("--path is required for traces")
                found = sources.generation_traces(cmd.path, cmd.days)
            else:
                key = os.environ.get("PHOENIX_API_KEY", "")  # only if your Phoenix has auth
                found = sources.phoenix(cmd.url, cmd.project, key)
            examples = [redact.redact(e, cmd.redact_extra) for e in found]
            out = cmd.out or _dir(cmd.name) / "raw.jsonl"
            write_jsonl(out, examples)
            print(f"{len(examples)} examples -> {out}")
        case Verify():
            kept, reasons = verify.verify(read_jsonl(cmd.src or _dir(cmd.name) / "raw.jsonl"))
            out = cmd.out or _dir(cmd.name) / "verified.jsonl"
            write_jsonl(out, kept)
            print(f"kept {len(kept)} -> {out}")
            for reason, n in sorted(reasons.items()):
                print(f"  dropped {n}: {reason}")
        case Review():
            from loupe.data.review import loop

            path = _ledger(cmd.name, cmd.ledger)
            examples = read_jsonl(cmd.src or _dir(cmd.name) / "verified.jsonl")
            loop(examples, path, cmd.by or os.environ.get("USER", ""), cmd.limit)
        case Curate():
            examples = read_jsonl(cmd.src or _dir(cmd.name) / "verified.jsonl")
            ledger = curate.load(_ledger(cmd.name, cmd.ledger))
            accepted, counts = curate.apply(examples, ledger)
            out = cmd.out or _dir(cmd.name) / "sft.jsonl"
            write_jsonl(out, accepted)
            print(f"{len(accepted)} examples -> {out}")
            print(json.dumps(counts))
        case Stats():
            sft = _dir(cmd.name) / "sft.jsonl"
            verified = _dir(cmd.name) / "verified.jsonl"
            examples = read_jsonl(sft) if sft.exists() else []
            ledger = curate.load(_ledger(cmd.name, None))
            waiting = curate.pending(read_jsonl(verified), ledger) if verified.exists() else []
            print(json.dumps({
                "examples": len(examples),
                "with_tool_calls": sum(1 for e in examples if e.tool_calls),
                "sources": sorted({e.meta.get("source", "") for e in examples} - {""}),
                "decisions": ledger.counts(),
                "unreviewed": len(waiting),
            }, indent=2))  # fmt: skip
