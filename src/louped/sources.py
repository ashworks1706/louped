"""The project's sources: the papers, docs, slides and notebooks its claims rest on, kept in
sources/ beside experiments/ and committed with them, so a claim can quote and cite them.

sources/index.json lists each one:
- key: what a citation names it by;
- title and kind (pdf, pptx, docx, ipynb, md, txt);
- file, under sources/;
- origin: the URL it came from, or None for a file you added;
- the sha256 of its file.

Its text is read page by page into a search index at <home>/sources.db, rebuilt from the files
whenever one changes, so the index is never committed. A page is a PDF page, a slide, a notebook
cell, or the whole of a Markdown, text or Word file (Word files have no fixed pages).

A URL is fetched once and kept. An arXiv page becomes its PDF and the paper's title. A shared
Google Doc or Slides deck becomes a PDF snapshot, because a quote must point at text that cannot
change under it. A notebook on GitHub, or opened from GitHub in Colab, is fetched raw.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import tempfile
import threading
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, TypeAdapter

from louped.core import documents
from louped.core.paths import NAME, experiments_dir, home, inside

Kind = Literal["pdf", "pptx", "docx", "ipynb", "md", "txt"]
#: The version of the readers in louped.core.documents the search index was built with: bump
#: it when they read a file differently, and every source is read again.
READER = 1
KINDS: dict[str, Kind] = {".pdf": "pdf", ".pptx": "pptx", ".docx": "docx", ".ipynb": "ipynb",
                          ".md": "md", ".markdown": "md", ".txt": "txt"}  # fmt: skip
#: The largest file a URL may bring in.
MAX_BYTES = 100 * 2**20
INDEX = "index.json"


class Source(BaseModel):
    key: str
    title: str
    kind: Kind
    #: Its file, relative to sources/.
    file: str
    #: The URL it was fetched from; None for a file added from disk.
    origin: str | None = None
    sha256: str
    #: When it was added (UTC).
    added: datetime
    pages: int


class Hit(BaseModel):
    key: str
    title: str
    page: int
    #: The matching words in [brackets], with a little text around them.
    snippet: str


class Pin(BaseModel):
    """A passage of a source someone marked: the quote as it stands on its page."""

    id: str
    key: str
    page: int
    exact: str
    #: Where the quote first stands in the page's text, spaces aside: the order pins are listed in.
    start: int = 0
    note: str | None = None
    #: What it bears on: refs (run:…, experiment:…) or the addresses of parts of a page.
    links: list[str] = []
    created: datetime


_LIST: TypeAdapter[list[Source]] = TypeAdapter(list[Source])
PINS = "pins.jsonl"
#: One writer of pins.jsonl at a time: the app and the agent can pin at once.
_PINNING = threading.Lock()


def sources_dir() -> Path:
    """sources/ at the project's root, beside experiments/."""
    return experiments_dir().parent / "sources"


def list_sources() -> list[Source]:
    """Every source in sources/index.json, by key; none when there is no index."""
    path = sources_dir() / INDEX
    if not path.is_file():
        return []
    return _LIST.validate_json(path.read_bytes())


def source(key: str) -> Source:
    """One source by key; KeyError naming the keys there are when it is not one."""
    found = {s.key: s for s in list_sources()}
    if key not in found:
        raise KeyError(f"no source {key!r}; there are {sorted(found)}")
    return found[key]


def is_url(location: str) -> bool:
    return re.match(r"^https?://", location) is not None


def add_source(location: str, key: str | None = None, title: str | None = None,
               transport: httpx.BaseTransport | None = None) -> Source:  # fmt: skip
    """Add a file or an https URL to sources/ (add_file, add_url)."""
    if is_url(location):
        return add_url(location, key, title, transport)
    return add_file(Path(location).expanduser(), key, title)


def add_url(url: str, key: str | None = None, title: str | None = None,
            transport: httpx.BaseTransport | None = None) -> Source:  # fmt: skip
    """Fetch a file from the internet into sources/, recording the URL it came from."""
    if not url.startswith("https://"):
        raise ValueError(f"{url} is not https: louped fetches over https only")
    resolved, found_title, suggested = _resolve(url, transport)
    data, kind = _fetch(resolved, transport)
    return _keep(data, kind, key, title, found_title, suggested, origin=url)


def add_file(path: Path, key: str | None = None, title: str | None = None) -> Source:
    """Copy a file into sources/. The server passes only a path already inside the project."""
    if not path.is_file():
        raise FileNotFoundError(f"no file {path}")
    return _keep(path.read_bytes(), _kind(path.name), key, title, None, path.stem, origin=None)


def _keep(data: bytes, kind: Kind, key: str | None, title: str | None, found_title: str | None,
          suggested: str, origin: str | None) -> Source:  # fmt: skip
    """Write a source's bytes and list it in the index, its text read to check it. A key already
    taken is refused unless it is the same file again, which returns the one there."""
    root = sources_dir()
    key = key or _slug(title or found_title or suggested)
    if not NAME.match(key):
        raise ValueError(f"{key!r} is not a source key: lowercase letters, digits and -")
    sha = hashlib.sha256(data).hexdigest()
    have = {s.key: s for s in list_sources()}
    if key in have:
        if have[key].sha256 == sha:
            return have[key]
        raise ValueError(f"{key} is already a source ({have[key].file}): give another key")
    target = inside(root, f"{key}.{'md' if kind == 'md' else kind}")
    root.mkdir(exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    try:
        text, own_title = _read(tmp, kind)
    except Exception as exc:
        tmp.unlink()
        raise ValueError(f"{origin or suggested} is not a readable {kind}: {exc}") from exc
    os.replace(tmp, target)
    added = Source(key=key, title=title or found_title or own_title or suggested, kind=kind,
                   file=target.name, origin=origin, sha256=sha, added=datetime.now(UTC),
                   pages=len(text))  # fmt: skip
    _write_index([*have.values(), added])
    return added


def page_text(key: str, page: int) -> str:
    """One page of a source's text, counted from 1."""
    found = source(key)
    pages, _ = _read(inside(sources_dir(), found.file), found.kind)
    if not 1 <= page <= len(pages):
        raise ValueError(f"{key} has pages 1 to {len(pages)}; there is no page {page}")
    return pages[page - 1]


def pins(key: str | None = None) -> list[Pin]:
    """The pins in sources/pins.jsonl, of one source or of all, by source, page and position."""
    path = sources_dir() / PINS
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    found = [Pin.model_validate_json(line) for line in lines if line.strip()]
    return [p for p in found if key is None or p.key == key]


def add_pin(key: str, page: int, quote: str, note: str | None = None,
            links: list[str] | None = None) -> Pin:  # fmt: skip
    """Pin a quote on a page of a source. The quote must be on that page, word for word (spaces
    and line breaks aside): a pin is never a paraphrase. Pinning the same quote again keeps one
    pin, with the note replaced when one is given and the links added to."""
    want = "".join(quote.split())
    if not want:
        raise ValueError("a pin quotes some words")
    found = find_quote(page_text(key, page), quote)
    if found is None:
        raise ValueError(f"{_flat(quote)[:80]!r} is not on page {page} of {key}: quote the words "
                         "as they stand there (source_page shows them)")  # fmt: skip
    at, exact = found
    pin_id = hashlib.sha256(f"{key}\n{page}\n{want}".encode()).hexdigest()[:10]
    with _PINNING:
        every = pins()
        old = next((p for p in every if p.id == pin_id), None)
        pin = Pin(id=pin_id, key=key, page=page, exact=exact, start=at,
                  note=note if note is not None else (old.note if old else None),
                  links=list(dict.fromkeys([*(old.links if old else []), *(links or [])])),
                  created=old.created if old else datetime.now(UTC))  # fmt: skip
        _write_pins([pin if p.id == pin_id else p for p in every] if old else [*every, pin])
    return pin


def find_quote(text: str, quote: str) -> tuple[int, str] | None:
    """Where a quote first stands in a page's text, and its words as they stand there. Compared
    with spaces and line breaks left out, as a selection in a PDF viewer may add or drop them at
    the ends of lines; None when it is not there."""
    want = "".join(quote.split())
    kept = [i for i, c in enumerate(text) if not c.isspace()]
    at = "".join(text[i] for i in kept).find(want) if want else -1
    if at < 0:
        return None
    return at, _flat(text[kept[at] : kept[at + len(want) - 1] + 1])


def delete_pin(pin_id: str) -> None:
    """Remove a pin; KeyError when there is none of that id."""
    with _PINNING:
        every = pins()
        if not any(p.id == pin_id for p in every):
            raise KeyError(f"no pin {pin_id!r}")
        _write_pins([p for p in every if p.id != pin_id])


def source_file(key: str) -> Path:
    """A source's file, for the app to show."""
    return inside(sources_dir(), source(key).file)


def _flat(text: str) -> str:
    """Text with every run of spaces and line breaks as one space, as a quote is compared."""
    return " ".join(text.split())


def _write_pins(found: list[Pin]) -> None:
    path = sources_dir() / PINS
    path.parent.mkdir(exist_ok=True)
    found = sorted(found, key=lambda p: (p.key, p.page, p.start))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp",
                                     delete=False) as tmp:  # fmt: skip
        tmp.write("".join(p.model_dump_json() + "\n" for p in found))
    os.replace(tmp.name, path)


def search(query: str, limit: int = 10) -> list[Hit]:
    """The pages that hold every word of query, best first."""
    words = re.findall(r"\w+", query)
    if not words:
        return []
    match = " ".join(f'"{w}"' for w in words)
    titles = {s.key: s.title for s in list_sources()}
    with closing(_index()) as db:
        rows = db.execute(
            "SELECT key, page, snippet(pages, 2, '[', ']', '…', 16) FROM pages "
            "WHERE pages MATCH ? ORDER BY rank LIMIT ?",
            (match, limit),
        ).fetchall()
    return [Hit(key=k, title=str(titles.get(k, k)), page=p, snippet=s) for k, p, s in rows]


def _index() -> sqlite3.Connection:
    """The search index, brought up to date with sources/: a changed file is read again, a
    removed one dropped."""
    home().mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(home() / "sources.db")
    if db.execute("PRAGMA user_version").fetchone()[0] != READER:  # read again by new readers
        db.executescript(f"DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS pages; "
                         f"PRAGMA user_version = {READER};")  # fmt: skip
    db.execute("CREATE TABLE IF NOT EXISTS files (key TEXT PRIMARY KEY, sha256 TEXT)")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(key UNINDEXED, "
               "page UNINDEXED, text, tokenize='porter unicode61')")  # fmt: skip
    have = dict(db.execute("SELECT key, sha256 FROM files").fetchall())
    now = {s.key: s for s in list_sources()}
    with db:
        for gone in have.keys() - now.keys():
            db.execute("DELETE FROM pages WHERE key = ?", (gone,))
            db.execute("DELETE FROM files WHERE key = ?", (gone,))
        for key, s in now.items():
            path = inside(sources_dir(), s.file)
            if have.get(key) == s.sha256 or not path.is_file():
                continue
            pages, _ = _read(path, s.kind)
            db.execute("DELETE FROM pages WHERE key = ?", (key,))
            db.executemany("INSERT INTO pages (key, page, text) VALUES (?, ?, ?)",
                           [(key, i, t) for i, t in enumerate(pages, 1)])  # fmt: skip
            db.execute("INSERT OR REPLACE INTO files VALUES (?, ?)", (key, s.sha256))
    return db


def _write_index(found: list[Source]) -> None:
    path = sources_dir() / INDEX
    tmp = path.with_suffix(".tmp")
    data = _LIST.dump_python(sorted(found, key=lambda s: s.key), mode="json")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _kind(name: str) -> Kind:
    suffix = Path(name).suffix.lower()
    if suffix not in KINDS:
        raise ValueError(f"{name}: louped reads {', '.join(sorted(KINDS))} files")
    return KINDS[suffix]


def _slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:48] or "source"


_ARXIV = re.compile(r"^https://(?:www\.)?arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?")
_GOOGLE = re.compile(r"^https://docs\.google\.com/(document|presentation)/d/([\w-]+)")
_GITHUB = re.compile(r"^https://(?:colab\.research\.google\.com/github|github\.com)/"
                     r"([^/]+)/([^/]+)/blob/(.+)$")  # fmt: skip


def _resolve(url: str, transport: httpx.BaseTransport | None) -> tuple[str, str | None, str]:
    """What to fetch for a URL, the title when the place says it, and a key to suggest."""
    if m := _ARXIV.match(url):
        paper = m.group(1)
        return f"https://arxiv.org/pdf/{paper}", _arxiv_title(paper, transport), f"arxiv-{paper}"
    if m := _GOOGLE.match(url):
        doc, ident = m.groups()
        export = "export?format=pdf" if doc == "document" else "export/pdf"
        return f"https://docs.google.com/{doc}/d/{ident}/{export}", None, f"google-{doc}"
    if m := _GITHUB.match(url):
        owner, repo, rest = m.groups()
        return (f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}", None,
                Path(rest).stem)  # fmt: skip
    if url.startswith("https://colab.research.google.com/"):
        raise ValueError("a Colab notebook kept in Google Drive needs your sign-in: download it "
                         "(File > Download .ipynb) and add the file")  # fmt: skip
    return url, None, Path(httpx.URL(url).path).stem or "source"


def _arxiv_title(paper: str, transport: httpx.BaseTransport | None) -> str | None:
    """The paper's title from arXiv's API."""
    with httpx.Client(transport=transport, timeout=30) as client:
        r = client.get("https://export.arxiv.org/api/query", params={"id_list": paper})
    r.raise_for_status()
    atom = "{http://www.w3.org/2005/Atom}"
    entry = ET.fromstring(r.text).find(f"{atom}entry")
    title = entry.findtext(f"{atom}title") if entry is not None else None
    return " ".join(title.split()) if title else None


def _public(request: httpx.Request) -> None:
    """Refuse a request to this machine or its network: a source comes from the internet."""
    host = request.url.host
    try:
        local = not ipaddress.ip_address(host).is_global
    except ValueError:
        local = host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
    if local:
        raise ValueError(f"{request.url} is not on the internet: louped fetches sources from "
                         "public addresses only")  # fmt: skip


def _fetch(url: str, transport: httpx.BaseTransport | None) -> tuple[bytes, Kind]:
    """A URL's bytes, at most MAX_BYTES, and their kind from the type the server gives."""
    hooks = {"request": [_public]}  # every request, redirects too
    with (httpx.Client(transport=transport, timeout=60, follow_redirects=True,
                       event_hooks=hooks) as client,
          client.stream("GET", url) as r):  # fmt: skip
        r.raise_for_status()
        if not str(r.url).startswith("https://"):
            raise ValueError(f"{url} redirected to {r.url}, which is not https")
        chunks, size = [], 0
        for chunk in r.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError(f"{url} is over {MAX_BYTES // 2**20} MB")
            chunks.append(chunk)
        kind_of = r.headers.get("content-type", "").split(";")[0].strip()
    data = b"".join(chunks)
    if kind_of == "application/pdf" or data.startswith(b"%PDF-"):
        return data, "pdf"
    if kind_of in ("text/html", "application/xhtml+xml"):
        raise ValueError(f"{url} is a web page, not a file: give the link to the PDF or file")
    return data, _kind(httpx.URL(url).path)


def _read(path: Path, kind: Kind) -> tuple[list[str], str | None]:
    """A source's text page by page, and the title its file gives, if any."""
    if kind == "pdf":
        return documents.pdf_pages(path)
    if kind == "pptx":
        return documents.pptx_slides(path)
    if kind == "docx":
        blocks, title = documents.docx_blocks(path)
        return ["\n".join(b.text for b in blocks)], title
    if kind == "ipynb":
        return documents.notebook_cells(path), None
    text = path.read_text(encoding="utf-8")
    heading = re.search(r"^# (.+)$", text, re.M) if kind == "md" else None
    return [text], heading.group(1).strip() if heading else None
