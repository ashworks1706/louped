"""`louped data ...`: the steps from a system's logged model calls to a reviewed training set.

Every step reads and writes under <home>/data/<name>/ unless given paths:
raw.jsonl (export or collect) -> verified.jsonl (verify) -> sft.jsonl (curate). The review ledger is
experiments/<name>/decisions.jsonl, in source control, because judgments cannot be regenerated.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import tyro

from louped.core import experiments_dir, home
from louped.data import curate, read_jsonl, redact, sources, verify, write_jsonl


def _dir(name: str) -> Path:
    return home() / "data" / name


def _ledger(name: str, given: Path | None) -> Path:
    return given or experiments_dir() / name / "decisions.jsonl"


@dataclass(frozen=True)
class Export:
    """Read a system's logged model calls, redact them, write raw.jsonl."""

    name: str
    """The dataset; also the experiments/ folder its ledger lives in."""
    source: Literal["traces", "phoenix"]
    path: Path | None = None
    """traces: the folder of .jsonl trace files, read at any depth."""
    url: str = "http://127.0.0.1:6006"
    """phoenix: the self-hosted Phoenix base URL."""
    project: str = "default"
    """phoenix: the project the spans are under."""
    span_kind: str = "openinference.span.kind"
    """phoenix: the span attribute that marks a model call (its value "llm", any case)."""
    span_name: str | None = None
    """phoenix: fetch only spans of this name."""
    days: int = 0
    """traces: skip files older than this; 0 reads every one."""
    redact_extra: tuple[str, ...] = ()
    """Extra redaction: a named pattern (id-10) or any regex."""
    out: Path | None = None


@dataclass(frozen=True)
class Collect:
    """Ask a teacher model each prompt and write its replies as raw.jsonl (distillation)."""

    name: str
    prompts: Path
    """JSONL, one prompt per line: a string, or a list of chat messages."""
    teacher: str
    """Any Inspect model, e.g. openai-api/vllm/Qwen/Qwen3-8B or louped/<saved model>."""
    system: str | None = None
    samples: int = 1
    max_tokens: int = 1024
    out: Path | None = None


@dataclass(frozen=True)
class Overlap:
    """List evaluation items that share a word n-gram with the training set (contamination)."""

    name: str
    evals: Path
    """JSONL with id and input per line, as Inspect's json dataset reads."""
    n: int = 13
    src: Path | None = None


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
    | Annotated[Collect, tyro.conf.subcommand("collect")]
    | Annotated[Overlap, tyro.conf.subcommand("overlap")]
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
                found = sources.phoenix(
                    cmd.url, cmd.project, key, kind_key=cmd.span_kind, span_name=cmd.span_name
                )
            examples = [redact.redact(e, cmd.redact_extra) for e in found]
            out = cmd.out or _dir(cmd.name) / "raw.jsonl"
            write_jsonl(out, examples)
            print(f"{len(examples)} examples -> {out}")
        case Collect():
            from louped.data.collect import collect

            lines = cmd.prompts.read_text(encoding="utf-8").splitlines()
            prompts = [json.loads(line) for line in lines if line.strip()]
            from louped.core import capture

            examples = collect(prompts, cmd.teacher, cmd.system, cmd.max_tokens, cmd.samples)
            out = cmd.out or _dir(cmd.name) / "raw.jsonl"
            write_jsonl(out, examples)
            capture().write(out.with_suffix(".meta.json"))
            print(f"{len(examples)} examples -> {out}")
        case Overlap():
            from louped.data.collect import overlap, plain

            train = read_jsonl(cmd.src or _dir(cmd.name) / "sft.jsonl")
            texts = [f"{plain(e.messages)} {e.reply}" for e in train]
            rows = [json.loads(line) for line in cmd.evals.read_text().splitlines() if line.strip()]
            evals = {str(r["id"]): plain(r["input"]) for r in rows}
            hit = overlap(texts, evals, cmd.n)
            print(json.dumps({"items": len(evals), "contaminated": len(hit), "ids": hit}))
        case Verify():
            kept, reasons = verify.verify(read_jsonl(cmd.src or _dir(cmd.name) / "raw.jsonl"))
            out = cmd.out or _dir(cmd.name) / "verified.jsonl"
            write_jsonl(out, kept)
            print(f"kept {len(kept)} -> {out}")
            for reason, n in sorted(reasons.items()):
                print(f"  dropped {n}: {reason}")
        case Review():
            from louped.data.review import loop

            path = _ledger(cmd.name, cmd.ledger)
            examples = read_jsonl(cmd.src or _dir(cmd.name) / "verified.jsonl")
            by = cmd.by or os.environ.get("USER")
            if not by:
                raise SystemExit("say who reviews with --by: each decision records it")
            loop(examples, path, by, cmd.limit)
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
