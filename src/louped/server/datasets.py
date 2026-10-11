"""The datasets a project works with, on the Datasets page of Behavior and of Efficiency:

- Hub datasets louped.toml lists ([hub] datasets), each under the sections [hub.domains] names
  (louped.server.hub); one it does not name shows under both;
- files under data/ at the project's root: JSONL, CSV, TSV, JSON and Parquet;
- the training sets louped already reads (louped.stores.training_sets), opened on their page.

A dataset's detail is its Hub card, license, size and downloads (hub.info), its splits and
features, and its first rows. A Hub dataset's rows come from the Hub's dataset viewer
(https://datasets-server.huggingface.co: /splits, /info, /first-rows), sent this machine's
Hugging Face token so gated datasets the account can open show too; a file's rows from the file.
What cannot be read is said with its reason, never shown as an empty table.

Listing reads only louped.toml and files, so it is on with --expose too; the Hub detail uses
this machine's token and is off there, like the rest of the Hub.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from louped.core.paths import inside
from louped.core.project import base
from louped.server import hub
from louped.server.hub import Domain, HubDetail
from louped.server.launch import Jobs
from louped.stores.boards import parse_rows
from louped.stores.training_sets import list_training_sets

VIEWER = "https://datasets-server.huggingface.co"
#: The folder at the project's root whose files are datasets.
DIR = "data"
FORMATS = ("jsonl", "ndjson", "csv", "tsv", "json", "parquet")
#: The most rows a detail shows; the viewer's first-rows gives 100.
MAX_ROWS = 100
#: A text file bigger than this is previewed from its first lines, without a row count.
MAX_PARSE = 32 * 2**20
TIMEOUT = 30


class Dataset(BaseModel):
    """One dataset the project has."""

    #: A Hub id, or a file's path from the project's root (data/x.jsonl).
    id: str
    source: Literal["hub", "local", "training"]
    #: The sections it is listed under; empty lists it under both.
    domains: list[Domain] = []
    #: A file's absolute path (a local file, a training set).
    path: str | None = None
    #: A file's format, by its suffix; a training set's recipe format (sft, dpo).
    format: str | None = None
    #: A file's bytes.
    size: int | None = None
    #: A training set's rows.
    rows: int | None = None
    error: str | None = None


class Feature(BaseModel):
    name: str
    #: Its type as the dataset declares it (string, int64, list<string>, class_label(...)).
    type: str


class Split(BaseModel):
    config: str
    split: str
    #: Its rows, when the viewer reports them.
    rows: int | None = None


class DatasetDetail(BaseModel):
    """One dataset's card, splits, features and first rows."""

    id: str
    source: Literal["hub", "local"]
    #: A Hub dataset's card excerpt, license, size and downloads.
    hub: HubDetail | None = None
    #: Why the Hub's own page could not be read.
    hub_error: str | None = None
    splits: list[Split] = []
    #: The config and split the rows are from.
    config: str | None = None
    split: str | None = None
    features: list[Feature] = []
    rows: list[dict[str, Any]] = []
    #: Rows in the split or file; None when unknown.
    total: int | None = None
    #: Why the splits, features or rows could not be read.
    error: str | None = None


class ViewerError(ValueError):
    """The dataset viewer was unreachable or refused, with its reason."""


def _get(url: str, params: dict[str, str], headers: dict[str, str]) -> httpx.Response:
    return httpx.get(url, params=params, headers=headers, timeout=TIMEOUT)


def viewer(path: str, **params: str | None) -> Any:
    """GET one of the dataset viewer's routes, with this machine's Hugging Face token when there
    is one; ViewerError with the reason when it is unreachable or answers an error."""
    from huggingface_hub import get_token

    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    asked = {k: v for k, v in params.items() if v is not None}
    try:
        got = _get(VIEWER + path, asked, headers)
    except httpx.HTTPError as exc:
        raise ViewerError(f"could not reach the dataset viewer: {exc}") from exc
    if got.status_code != 200:
        try:
            said = got.json().get("error") or got.text
        except ValueError:
            said = got.text
        raise ViewerError(f"the dataset viewer answered {got.status_code} for {path}: "
                          f"{str(said)[:300]}")  # fmt: skip
    return got.json()


def type_name(t: Any) -> str:
    """A datasets feature type as one short text."""
    if isinstance(t, list):
        return f"list<{type_name(t[0])}>" if t else "list"
    if not isinstance(t, dict):
        return str(t)
    kind = t.get("_type")
    if kind == "Value":
        return str(t.get("dtype", "value"))
    if kind == "ClassLabel":
        names = [str(n) for n in t.get("names") or []]
        shown = ", ".join(names[:6]) + (", …" if len(names) > 6 else "")
        return f"class_label({shown})" if names else "class_label"
    if kind in ("Sequence", "List", "LargeList"):
        return f"list<{type_name(t.get('feature'))}>"
    return "struct" if kind is None else str(kind).lower()


def hub_splits(id: str) -> list[Split]:
    found = viewer("/splits", dataset=id)
    return [Split(config=s["config"], split=s["split"]) for s in found.get("splits", [])]


def hub_features(id: str, config: str, split: str) -> list[Feature]:
    """A split's features, from the viewer's /info (else its first rows)."""
    try:
        info = viewer("/info", dataset=id, config=config)["dataset_info"]
        return [Feature(name=k, type=type_name(v)) for k, v in info["features"].items()]
    except (ViewerError, KeyError, TypeError):
        first = viewer("/first-rows", dataset=id, config=config, split=split)
        return [Feature(name=f["name"], type=type_name(f["type"])) for f in first["features"]]


def hub_detail(id: str, config: str | None, split: str | None, rows: int) -> DatasetDetail:
    """A Hub dataset: its page (hub.info), its splits with their sizes, and the first rows of
    one split (config and split, else the first the viewer lists)."""
    out = DatasetDetail(id=id, source="hub")
    try:
        out.hub = hub.info("datasets", id)
    except HTTPException as exc:
        out.hub_error = str(exc.detail)
    try:
        out.splits = hub_splits(id)
        if not out.splits:
            raise ViewerError("the dataset viewer lists no splits for it")
        configs = list(dict.fromkeys(s.config for s in out.splits))
        out.config = config or configs[0]
        if out.config not in configs:
            raise ViewerError(f"no config {out.config}; it has {', '.join(configs)}")
        mine = [s.split for s in out.splits if s.config == out.config]
        out.split = split or mine[0]
        if out.split not in mine:
            raise ViewerError(f"no split {out.split} in {out.config}; it has {', '.join(mine)}")
        try:
            info = viewer("/info", dataset=id, config=out.config)["dataset_info"]
            sizes = {k: v.get("num_examples") for k, v in (info.get("splits") or {}).items()}
            for s in out.splits:
                s.rows = sizes.get(s.split) if s.config == out.config else None
            out.features = [Feature(name=k, type=type_name(v))
                            for k, v in (info.get("features") or {}).items()]  # fmt: skip
        except ViewerError:
            pass  # sizes and features then come from the first rows
        first = viewer("/first-rows", dataset=id, config=out.config, split=out.split)
        if not out.features:
            out.features = [Feature(name=f["name"], type=type_name(f["type"]))
                            for f in first.get("features", [])]  # fmt: skip
        out.rows = [r["row"] for r in first.get("rows", [])][:rows]
        out.total = next((s.rows for s in out.splits
                          if s.config == out.config and s.split == out.split), None)  # fmt: skip
    except ViewerError as exc:
        out.error = str(exc)
    return out


def data_dir() -> Path:
    return base() / DIR


def _local_files() -> list[Path]:
    folder = data_dir()
    if not folder.is_dir():
        return []
    found = (p for p in folder.rglob("*") if p.is_file() and p.suffix[1:].lower() in FORMATS)
    return sorted(
        p for p in found if not any(x.startswith(".") for x in p.relative_to(folder).parts)
    )


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "float64"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return f"list<{_kind(value[0])}>" if value else "list"
    return (
        "struct" if isinstance(value, dict) else "null" if value is None else type(value).__name__
    )


def _head(path: Path, rows: int) -> bytes:
    """The first lines of a text file: a CSV's header and rows, or rows of JSONL."""
    lines: list[bytes] = []
    with path.open("rb") as f:
        for line in f:
            lines.append(line)
            if len(lines) > rows:
                break
    return b"".join(lines)


def local_detail(name: str, rows: int) -> DatasetDetail:
    """A file under data/ (name is its path from the project's root): its columns with their
    types and its first rows."""
    try:
        path = inside(base(), *name.split("/"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if data_dir().resolve() not in path.resolve().parents or not path.is_file():
        raise HTTPException(404, f"no dataset {name} under {DIR}/")
    suffix = path.suffix[1:].lower()
    out = DatasetDetail(id=name, source="local", split=suffix)
    try:
        if suffix == "parquet":
            import pyarrow.parquet as pq

            file = pq.ParquetFile(path)
            out.total = file.metadata.num_rows
            out.features = [Feature(name=f.name, type=str(f.type)) for f in file.schema_arrow]
            batch = next(file.iter_batches(batch_size=rows), None)
            out.rows = batch.to_pylist() if batch is not None else []
            return out
        if suffix not in FORMATS:
            raise ValueError(f"{name}: a dataset file is one of {', '.join(FORMATS)}")
        big = path.stat().st_size > MAX_PARSE
        if big and suffix == "json":
            raise ValueError(f"{name} is over {MAX_PARSE // 2**20} MB of JSON; keep it as JSONL "
                             "or Parquet to preview it")  # fmt: skip
        found = parse_rows(_head(path, rows) if big else path.read_bytes(), name)
        out.total = None if big else len(found)
        out.rows = found[:rows]
        columns: dict[str, str] = {}
        for row in out.rows:
            for k, v in row.items():
                if columns.get(k, "null") == "null":
                    columns[k] = _kind(v)
        out.features = [Feature(name=k, type=v) for k, v in columns.items()]
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        out.error = str(exc)
    return out


def list_datasets() -> list[Dataset]:
    """The Hub datasets louped.toml lists, the files under data/, then the training sets louped
    reads that are not among those files."""
    tags = hub.dataset_domains()
    out = [Dataset(id=d, source="hub", domains=tags.get(d, [])) for d in hub.added().datasets]
    files = _local_files()
    root = base()
    for path in files:
        out.append(Dataset(id=path.relative_to(root).as_posix(), source="local",
                           path=str(path.resolve()), format=path.suffix[1:].lower(),
                           size=path.stat().st_size))  # fmt: skip
    seen = {str(p.resolve()) for p in files}
    for s in list_training_sets():
        if s.path not in seen:
            out.append(Dataset(id=Path(s.path).name, source="training", path=s.path,
                               format=s.format, rows=s.rows, error=s.error))  # fmt: skip
    return out


def router(jobs: Jobs | None) -> APIRouter:
    api = APIRouter(prefix="/api/datasets")

    def _rows(rows: int) -> int:
        return min(max(rows, 1), MAX_ROWS)

    @api.get("")
    def datasets() -> list[Dataset]:
        """Every dataset the project has, each with the sections it is listed under (none:
        both)."""
        try:
            return list_datasets()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.get("/hub")
    def hub_dataset(id: str, config: str | None = None, split: str | None = None,
                    rows: int = 20) -> DatasetDetail:  # fmt: skip
        """A Hub dataset's page, splits, features and first rows; what could not be read is
        said in hub_error and error."""
        if jobs is None:
            raise HTTPException(403, "the Hub is off: this server was started with --expose")
        if not re.match(hub.REPO, id):
            raise HTTPException(400, f"{id!r} is not a Hub id")
        return hub_detail(id, config or None, split or None, _rows(rows))

    @api.get("/local")
    def local_dataset(path: str, rows: int = 20) -> DatasetDetail:
        """A file under data/: its columns and first rows, by its path from the project's
        root."""
        return local_detail(path, _rows(rows))

    return api
