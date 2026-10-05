"""A read-only copy of the dashboard as static files, to put on any static host.

`louped publish OUT` writes the built UI and, beside it, every API answer its pages ask for over
this home's runs: api/<key>.json, where key is the request's path and query as
encodeURIComponent writes it with each % as a comma (the UI's api.ts reads them the same way in
snapshot mode, which a meta tag in each page turns on). Artifacts keep their own paths, so links to
them work; Inspect View is bundled at inspect/ and circuit-tracer's viewer copied to circuit/.

Nothing in it runs: launching, the Playground and labelling are off, and comparisons of two runs are
not in it. It must be served at a domain's root (an HF static Space, a Vercel project, a GitHub
Pages user site), since the UI asks for /api/... from the root.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.testclient import TestClient

from louped.core import graphs_dir, logs_dir
from louped.server.app import create_app

#: What encodeURIComponent leaves as it is, besides letters and digits.
JS_SAFE = "-_.!~*'()"
#: Artifacts bigger than this stay out; the run page offers them as a download, which then fails.
MAX_ARTIFACT = 16 * 2**20
SNAPSHOT = '<meta name="louped-snapshot" content="1">'


@dataclass
class Published:
    out: Path
    runs: int = 0
    files: int = 0
    #: Artifacts left out for their size.
    skipped: list[str] = field(default_factory=list)
    #: Requests the API did not answer, so the page asking for them shows an error.
    failed: list[str] = field(default_factory=list)


def _enc(text: str) -> str:
    return quote(text, safe=JS_SAFE)


#: Longer keys are hashed: file systems allow 255 bytes a name.
MAX_KEY = 200


def key(path: str) -> str:
    """A request's snapshot file name: the path and query encoded, with no % a host would decode;
    over MAX_KEY, its SHA-256 instead (api.ts does the same)."""
    found = _enc(path).replace("%", ",")
    return found if len(found) <= MAX_KEY else "h-" + hashlib.sha256(found.encode()).hexdigest()


def publish(out: Path, web: Path) -> Published:
    """Write the dashboard over this home's runs as static files at out, which must be empty."""
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} is not empty")
    shutil.copytree(web, out, dirs_exist_ok=True)
    for page in out.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        page.write_text(html.replace("<head>", "<head>" + SNAPSHOT, 1), encoding="utf-8")
    done = Published(out)
    api = TestClient(create_app(launching=False), base_url="http://localhost")

    def save(path: str, expected: bool = True) -> Any:
        got = api.get("/api" + path)
        if got.status_code != 200:
            if expected:
                done.failed.append(f"{path}: {got.status_code}")
            return None
        target = out / "api" / f"{key(path)}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(got.content)
        done.files += 1
        return got.json()

    for path in ("/health", "/vectors", "/graphs", "/ui/layout", "/ui/theme"):
        save(path)
    save("/playground", expected=False)  # no model is loaded in a snapshot
    layouts: set[str] = set()  # each run's page asks for its experiment's, listed or not
    for experiment in save("/experiments") or []:
        save(f"/experiments/{_enc(experiment['name'])}")
        layouts.add(experiment["name"])
        save(f"/ui/layout?experiment={_enc(experiment['name'])}")
    for run in save("/runs") or []:
        done.runs += 1
        rid = _enc(run["id"])
        detail = save(f"/runs/{rid}") or {}
        if (named := run.get("experiment")) and named not in layouts:
            layouts.add(named)
            save(f"/ui/layout?experiment={_enc(named)}")
        evaled = run["id"].startswith("e-")
        for sample in save(f"/runs/{rid}/samples", expected=evaled) or []:
            save(f"/runs/{rid}/samples/{_enc(sample['id'])}?epoch={sample['epoch']}")
        save(f"/runs/{rid}/views")
        save(f"/runs/{rid}/labels", expected=evaled)
        save(f"/runs/{rid}/agreement", expected=False)  # a judge run's only
        for feature in save(f"/runs/{rid}/features", expected=False) or []:
            save(f"/runs/{rid}/features/{feature}")
        for artifact in detail.get("artifacts", []):
            _artifact(api, out, run["id"], artifact, done)
    _viewers(out)
    return done


def _artifact(
    api: TestClient, out: Path, run: str, artifact: dict[str, Any], done: Published
) -> None:
    """One artifact at the path the UI links it by."""
    if (artifact.get("size") or 0) > MAX_ARTIFACT:
        done.skipped.append(f"{run}/{artifact['path']}")
        return
    segments = "/".join(_enc(s) for s in artifact["path"].split("/"))
    got = api.get(f"/api/runs/{_enc(run)}/artifacts/{segments}")
    if got.status_code != 200:
        done.failed.append(f"{run}/{artifact['path']}: {got.status_code}")
        return
    # a static host decodes the URL, so the file goes at the decoded path
    folder = (out / "api" / "runs" / run / "artifacts").resolve()
    target = (folder / artifact["path"]).resolve()
    if not target.is_relative_to(folder):
        raise ValueError(f"{run}: artifact path {artifact['path']!r} leaves its run")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(got.content)
    done.files += 1


def _viewers(out: Path) -> None:
    """Inspect View over the eval logs, and circuit-tracer's viewer with its graphs."""
    logs = logs_dir()
    if logs.is_dir() and any(logs.glob("*.eval")):
        from inspect_ai.log import bundle_log_dir

        bundle_log_dir(str(logs), str(out / "inspect"), overwrite=True)
    graphs = graphs_dir()
    if (graphs / "viewer").is_dir() and any((graphs / "viewer").iterdir()):
        shutil.copytree(graphs / "viewer", out / "circuit")
        data = [p for p in graphs.iterdir() if p.is_file()]
        for folder in ("data", "graph_data"):
            (out / "circuit" / folder).mkdir()
            for path in data:
                shutil.copy2(path, out / "circuit" / folder / path.name)


def describe(done: Published) -> str:
    """What publish wrote, and where it can go."""
    lines = [f"{done.runs} runs, {done.files} files in {done.out}"]
    if done.skipped:
        lines.append(f"left out for size: {json.dumps(done.skipped)}")
    if done.failed:
        lines.append(f"not answered, so their pages show an error: {json.dumps(done.failed)}")
    lines.append("Serve it at a domain's root: an HF static Space, Vercel, or a GitHub Pages user "
                 "site.")  # fmt: skip
    return "\n".join(lines)
