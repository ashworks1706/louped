"""The Hugging Face Hub in the app: search models, embedding models, datasets and papers, read one,
and add it to the project.

Every call goes through huggingface_hub's HfApi with the token on this machine (where `hf auth
login` and the remote's Connect dialog keep it, louped.sync), so the gated and private
repositories the account can see show too. What a project adds is listed in its louped.toml:

    [hub]
    models = ["Qwen/Qwen2.5-0.5B-Instruct"]
    embeddings = ["BAAI/bge-small-en-v1.5"]
    datasets = ["openai/gsm8k"]

and the app's model fields offer them. A paper becomes a source (louped.sources) from its arXiv
page, so it is searched and cited like any other. A download is a job (`louped hub get`) on the
queue, so it shows on Runs.

The Hub uses this machine's token, and adding writes the project, so all of it is off with
--expose, like launching.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Iterable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from louped import sources as library
from louped import sync
from louped.core.project import FILE, config, root
from louped.server.launch import Job, Jobs, LaunchRequest, require_json

Kind = Literal["models", "embeddings", "datasets", "papers"]
Sort = Literal["downloads", "likes", "recent"]
#: The pipeline tags of a model that turns text into a vector.
EMBEDDING_TASKS = ("sentence-similarity", "feature-extraction")
#: How the Hub names each sort.
SORTS = {"downloads": "downloads", "likes": "likes", "recent": "last_modified"}
#: The fields a model search asks for: list_models returns only these with expand.
MODEL_FIELDS = ["downloads", "likes", "pipeline_tag", "library_name", "gated", "private",
                "lastModified", "safetensors"]  # fmt: skip
DATASET_FIELDS = ["downloads", "likes", "gated", "private", "lastModified"]
#: A repository id: <owner>/<name>, or a bare <name> for the oldest models.
REPO = r"^[\w.-]+(/[\w.-]+)?$"
#: A paper on the Hub is named by its arXiv id.
PAPER = r"^\d{4}\.\d{4,5}$"
#: How much of a card the detail shows.
CARD_CHARS = 2000
SITE = "https://huggingface.co"


class Account(BaseModel):
    #: Whether a Hugging Face token is on this machine.
    token: bool
    #: The account the token belongs to.
    name: str | None = None
    avatar: str | None = None
    #: Why the token on this machine was refused.
    error: str | None = None


class Token(BaseModel):
    token: str = Field(min_length=1)


class HubHit(BaseModel):
    """One model, dataset or paper a search found."""

    kind: Kind
    id: str
    #: Its page on the Hub.
    url: str
    downloads: int | None = None
    likes: int | None = None
    #: A model's pipeline tag, such as text-generation.
    task: str | None = None
    library: str | None = None
    #: A gated repository needs access asked for on its page first.
    gated: bool = False
    private: bool = False
    updated: datetime | None = None
    #: A model's parameter count, from its safetensors files.
    params: int | None = None
    #: A paper's title, authors and upvotes.
    title: str | None = None
    authors: list[str] = []
    upvotes: int | None = None


class HubDetail(HubHit):
    #: The start of its card (README) after the metadata; None when it has none or it is gated.
    card: str | None = None
    license: str | None = None
    tags: list[str] = []
    #: Bytes the repository takes on the Hub.
    size: int | None = None
    files: int | None = None
    #: A paper's abstract.
    summary: str | None = None
    #: Where else to read it: arxiv, github, project.
    links: dict[str, str] = {}


class HubAdded(BaseModel):
    """What the project lists under [hub] in louped.toml."""

    models: list[str] = []
    embeddings: list[str] = []
    datasets: list[str] = []


class AddRequest(BaseModel):
    kind: Kind
    id: str = Field(pattern=REPO)
    #: For a model or dataset: also download it here, as a job.
    download: bool = False


class AddResult(BaseModel):
    added: HubAdded
    #: The source a paper became.
    source: library.Source | None = None
    #: The download's job.
    job: Job | None = None


def _api() -> Any:
    from huggingface_hub import HfApi

    return HfApi()


def url_of(kind: Kind, id: str) -> str:
    where = {"datasets": "datasets/", "papers": "papers/"}.get(kind, "")
    return f"{SITE}/{where}{id}"


def _hub[T](call: Callable[[], T]) -> T:
    """A Hub call, its errors said as HTTP errors: a refused token 401, no access 403, no such
    repository 404, the Hub unreachable or failing 502."""
    from huggingface_hub.errors import (
        EntryNotFoundError,
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
    )

    try:
        return call()
    except GatedRepoError as exc:
        raise HTTPException(403, f"gated: ask for access on its Hub page first. {exc}") from exc
    except (RepositoryNotFoundError, EntryNotFoundError) as exc:
        raise HTTPException(404, f"not on the Hub, or not visible to this token: {exc}") from exc
    except HfHubHTTPError as exc:
        if exc.response.status_code == 401:
            raise HTTPException(401, f"Hugging Face refused the token: {exc}") from exc
        raise HTTPException(502, f"the Hugging Face Hub answered: {exc}") from exc
    except (httpx.HTTPError, OSError) as exc:
        raise HTTPException(502, f"could not reach the Hugging Face Hub: {exc}") from exc


def _model(info: Any, kind: Kind) -> dict[str, Any]:
    return {"kind": kind, "id": info.id, "url": url_of(kind, info.id), "downloads": info.downloads,
            "likes": info.likes, "task": info.pipeline_tag, "library": info.library_name,
            "gated": bool(info.gated), "private": bool(info.private),
            "updated": info.last_modified,
            "params": info.safetensors.total if info.safetensors else None}  # fmt: skip


def _dataset(info: Any) -> dict[str, Any]:
    return {"kind": "datasets", "id": info.id, "url": url_of("datasets", info.id),
            "downloads": info.downloads, "likes": info.likes, "gated": bool(info.gated),
            "private": bool(info.private), "updated": info.last_modified}  # fmt: skip


def _paper(info: Any) -> dict[str, Any]:
    return {"kind": "papers", "id": info.id, "url": url_of("papers", info.id),
            "title": info.title, "authors": [a.name for a in info.authors or [] if a.name],
            "upvotes": info.upvotes, "updated": info.published_at}  # fmt: skip


def search(kind: Kind, q: str = "", task: str | None = None, library_name: str | None = None,
           sort: Sort = "downloads", limit: int = 20) -> list[HubHit]:  # fmt: skip
    """Models, embedding models (a model whose pipeline tag is one of EMBEDDING_TASKS) or datasets
    matching q, sorted, most first; papers matching q, or today's daily papers when q is empty.
    task and library filter models only; sort does not apply to papers."""
    api, query = _api(), q.strip() or None
    if kind in ("datasets", "papers") and (task or library_name):
        raise HTTPException(400, "task and library filter models and embeddings only")
    if kind == "papers":
        papers = _hub(lambda: list(api.list_papers(query=query, limit=limit) if query
                                   else api.list_daily_papers(limit=limit)))  # fmt: skip
        return [HubHit(**_paper(p)) for p in papers]
    if kind == "datasets":
        sets = _hub(lambda: list(api.list_datasets(search=query, sort=SORTS[sort], limit=limit,
                                                   expand=DATASET_FIELDS)))  # fmt: skip
        return [HubHit(**_dataset(d)) for d in sets]
    if kind == "embeddings" and task is not None and task not in EMBEDDING_TASKS:
        raise HTTPException(400, f"an embedding model's task is one of {list(EMBEDDING_TASKS)}")
    tasks: Iterable[str | None] = [task] if task or kind == "models" else EMBEDDING_TASKS

    def each(tag: str | None) -> list[Any]:
        return list(api.list_models(search=query, pipeline_tag=tag, filter=library_name,
                                    sort=SORTS[sort], limit=limit,
                                    expand=MODEL_FIELDS))  # fmt: skip

    hits = [HubHit(**_model(m, kind)) for tag in tasks for m in _hub(partial(each, tag))]
    if len(hits) > limit:  # embeddings: both tasks' lists, merged by the sort
        key = {"downloads": lambda h: h.downloads or 0, "likes": lambda h: h.likes or 0,
               "recent": lambda h: h.updated.timestamp() if h.updated else 0}[sort]  # fmt: skip
        hits = sorted(hits, key=key, reverse=True)[:limit]
    return hits


def _card(id: str, repo_type: str) -> str | None:
    """The start of a repository's README after its metadata block; None when it has none, or
    when it is gated and this account has no access yet (the detail says gated)."""
    from huggingface_hub.errors import EntryNotFoundError, GatedRepoError
    from huggingface_hub.repocard import REGEX_YAML_BLOCK

    try:
        path = _api().hf_hub_download(id, "README.md", repo_type=repo_type)
    except (EntryNotFoundError, GatedRepoError):
        return None
    text = REGEX_YAML_BLOCK.sub("", Path(path).read_text(encoding="utf-8"), count=1).strip()
    return text[:CARD_CHARS] + ("…" if len(text) > CARD_CHARS else "")


def _license(info: Any) -> str | None:
    if info.card_data is not None and (found := info.card_data.get("license")):
        return str(found)
    return next((t.removeprefix("license:") for t in info.tags or []
                 if t.startswith("license:")), None)  # fmt: skip


def info(kind: Kind, id: str) -> HubDetail:
    """One model, dataset or paper in full: its card's start, license, tags, size and files; for
    a paper its abstract and links."""
    api = _api()
    if kind == "papers":
        if not re.match(PAPER, id):
            raise HTTPException(400, f"{id} is not an arXiv id, which names a paper on the Hub")
        p = _hub(lambda: api.paper_info(id))
        links = {"arxiv": f"https://arxiv.org/abs/{id}"}
        links |= {"github": p.github_repo} if p.github_repo else {}
        links |= {"project": p.project_page} if p.project_page else {}
        return HubDetail(**_paper(p), summary=p.summary, links=links)
    repo_type = "dataset" if kind == "datasets" else "model"
    if kind == "datasets":
        expand = [*DATASET_FIELDS, "cardData", "siblings", "usedStorage", "tags"]
        d = _hub(lambda: api.dataset_info(id, expand=expand))
        found = _dataset(d)
    else:
        expand = [*MODEL_FIELDS, "cardData", "siblings", "usedStorage", "tags"]
        d = _hub(lambda: api.model_info(id, expand=expand))
        found = _model(d, kind)
    return HubDetail(**found, card=_hub(lambda: _card(id, repo_type)), license=_license(d),
                     tags=list(d.tags or []), size=d.used_storage,
                     files=len(d.siblings) if d.siblings is not None else None)  # fmt: skip


def added() -> HubAdded:
    """The [hub] table of the project's louped.toml; nothing when it has none."""
    table = config().get("hub", {})
    try:
        return HubAdded.model_validate(table)
    except ValueError as exc:
        raise ValueError(f"{FILE} [hub]: each of models, embeddings, datasets is a list of "
                         f"repository ids: {exc}") from exc  # fmt: skip


def _write(key: str, ids: list[str]) -> None:
    """Set `key = [...]` in louped.toml's [hub] table, one line, the rest of the file (comments
    too) as it was."""
    found = root()
    if found is None:
        raise ValueError("not in a louped project: run louped init first")
    path = found / FILE
    line = f"{key} = {json.dumps(ids)}"
    lines = path.read_text(encoding="utf-8").splitlines()
    head = next((i for i, x in enumerate(lines) if re.match(r"\s*\[hub\]\s*(#.*)?$", x)), None)
    if head is None:
        lines += [*([""] if lines and lines[-1].strip() else []), "[hub]", line]
    else:
        end = next((i for i in range(head + 1, len(lines)) if lines[i].lstrip().startswith("[")),
                   len(lines))  # fmt: skip
        at = next((i for i in range(head + 1, end) if re.match(rf"\s*{key}\s*=", lines[i])), None)
        if at is None:
            lines.insert(head + 1, line)
        else:
            lines[at] = line
    text = "\n".join(lines) + "\n"
    try:
        written = tomllib.loads(text).get("hub", {}).get(key)
    except tomllib.TOMLDecodeError:
        written = None
    if written != ids:
        raise ValueError(f"{path}: could not set [hub] {key} there; add {line} by hand")
    path.write_text(text, encoding="utf-8")


def add(kind: Kind, id: str) -> HubAdded:
    """List a model, embedding model or dataset under [hub] in louped.toml, once."""
    if kind == "papers":
        raise ValueError("a paper is added as a source")
    have = added()
    listed: list[str] = getattr(have, kind)
    if id not in listed:
        _write(kind, [*listed, id])
    return added()


def router(jobs: Jobs | None) -> APIRouter:
    api = APIRouter(prefix="/api/hub")

    def on() -> None:
        if jobs is None:
            raise HTTPException(403, "the Hub is off: this server was started with --expose")

    @api.get("/me", dependencies=[Depends(on)])
    def me() -> Account:
        """Whether a Hugging Face token is on this machine, and whose it is; a refused token is
        said in error."""
        if not sync.has_token():
            return Account(token=False)
        try:
            who = _hub(lambda: _api().whoami())
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
            return Account(token=True, error=str(exc.detail))
        avatar = who.get("avatarUrl")
        if avatar and avatar.startswith("/"):
            avatar = SITE + avatar
        return Account(token=True, name=who.get("name"), avatar=avatar)

    @api.post("/token", dependencies=[Depends(on), Depends(require_json)])
    def token(req: Token) -> Account:
        """Check a token and keep it where huggingface_hub keeps it, not in the project."""
        try:
            name = _hub(lambda: sync.save_token(req.token.strip()))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Account(token=True, name=name)

    @api.get("/search", dependencies=[Depends(on)])
    def hub_search(kind: Kind, q: str = "", task: str | None = None,
                   library: str | None = None, sort: Sort = "downloads",
                   limit: int = 20) -> list[HubHit]:  # fmt: skip
        return search(kind, q, task or None, library or None, sort, min(max(limit, 1), 100))

    @api.get("/info", dependencies=[Depends(on)])
    def hub_info(kind: Kind, id: str) -> HubDetail:
        if not re.match(REPO, id):
            raise HTTPException(400, f"{id!r} is not a Hub id")
        return info(kind, id)

    @api.get("/added", dependencies=[Depends(on)])
    def hub_added() -> HubAdded:
        try:
            return added()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/add", dependencies=[Depends(on), Depends(require_json)])
    def hub_add(req: AddRequest) -> AddResult:
        """A model, embedding model or dataset listed in louped.toml, and with download fetched
        here as a job; a paper kept in sources/ from its arXiv page."""
        assert jobs is not None  # on() refused otherwise
        if req.kind == "papers":
            if req.download:
                raise HTTPException(400, "a paper is added to sources, not downloaded")
            if not re.match(PAPER, req.id):
                raise HTTPException(400, f"{req.id} is not an arXiv id")
            url = f"https://arxiv.org/abs/{req.id}"
            try:
                kept = library.add_url(url)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(502, f"could not fetch {url}: {exc}") from exc
            return AddResult(added=added(), source=kept)
        try:
            listed = add(req.kind, req.id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        job = None
        if req.download:
            dataset = {"--dataset": True} if req.kind == "datasets" else {}
            launch = LaunchRequest(id="hub", options={"action": "get", "repo": req.id, **dataset})
            what = " --dataset" if dataset else ""
            job = jobs.submit(launch, f"louped hub get {req.id}{what}")
        return AddResult(added=listed, job=job)

    return api
