"""The FastAPI app: the API under /api, Inspect View at /inspect, circuit-tracer's graph viewer at
/circuit, and the built UI at / when there is one.

The server owns no database. Every route reads a store another tool already writes (MLflow,
Inspect logs, artifact files, experiments/), so deleting the server loses nothing. The one thing
it writes itself is a person's labels on a judge run's pairs, plain JSON under <home>/labels. The
launch routes start louped's own commands as jobs, whose runs land in those same stores.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from louped import __version__, stores
from louped.core import Direction, home
from louped.server import graphs, inspect_view, launch, playground
from louped.stores.labels import Label
from louped.stores.runs import read_artifact
from louped.stores.types import (
    Agreement,
    Comparison,
    Experiment,
    ExperimentDetail,
    FeatureDashboard,
    Graph,
    RunDetail,
    RunSummary,
    RunView,
    SampleDetail,
    SampleSummary,
)
from louped.sync import configured

#: Where the UI's dev server runs; allowed to call the API during development only.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

#: The Host headers answered by default: this machine only, so a page on another site cannot
#: reach the API through a rebound DNS name.
LOOPBACK = ["localhost", "127.0.0.1", "::1", "[::1]"]


class LabelRequest(BaseModel):
    #: The person's pick for the pair, or null to clear it.
    label: Label | None


class Text(BaseModel):
    """A Markdown file's text."""

    text: str


class Health(BaseModel):
    status: str
    version: str
    home: str
    #: Whether this server runs jobs; the UI only watches jobs when it does.
    launching: bool = False
    #: Where runs are pushed and pulled; null when none is set or launching is off.
    remote: str | None = None


def find_ui(given: Path | None = None) -> Path | None:
    """The UI to serve: the one given; else the export a release carries in louped/web; else a
    source checkout's apps/web/out. Says which, or that there is none and the API runs alone."""
    if given is not None:
        return given
    package = Path(__file__).resolve().parents[1]
    for found in (package / "web", package.parents[1] / "apps" / "web" / "out"):
        if (found / "index.html").is_file():
            print(f"UI: {found}")
            return found
    print("no UI found: the API only. In a checkout, build it with `just web-build`.")
    return None


def create_app(
    web_dir: Path | None = None,
    hosts: list[str] | None = None,
    launching: bool = False,
) -> FastAPI:
    """The app. With web_dir, the static UI export is served at /. hosts are the Host headers it
    answers, loopback by default. launching lets the UI start experiments, training and evals as
    jobs on this machine and load a model into the Playground."""
    app = FastAPI(
        title="louped",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts or LOOPBACK)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(stores.NotFound)
    async def not_found(_: Request, exc: stores.NotFound) -> JSONResponse:
        return JSONResponse({"detail": f"not found: {exc}"}, status_code=404)

    @app.exception_handler(stores.BadExperiment)
    async def bad_experiment(_: Request, exc: stores.BadExperiment) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=500)

    def editing() -> None:
        if not launching:
            raise HTTPException(403, "editing is off: this server was started with --expose")

    @app.get("/api/health")
    def health() -> Health:
        return Health(status="ok", version=__version__, home=str(home()), launching=launching,
                      remote=configured() if launching else None)  # fmt: skip

    @app.get("/api/runs")
    def runs() -> list[RunSummary]:
        return stores.list_runs()

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> RunDetail:
        return stores.get_run(run_id)

    @app.get("/api/runs/{run_id}/samples")
    def samples(run_id: str) -> list[SampleSummary]:
        return stores.list_samples(run_id)

    @app.get("/api/runs/{run_id}/samples/{sample_id}")
    def sample(run_id: str, sample_id: str, epoch: int = 1) -> SampleDetail:
        return stores.get_sample(run_id, sample_id, epoch)

    @app.get("/api/runs/{run_id}/artifacts/{path:path}")
    def artifact(run_id: str, path: str) -> Response:
        if ".." in Path(path).parts:
            raise HTTPException(400, "bad path")
        media = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return Response(read_artifact(run_id, path), media_type=media)

    @app.put(
        "/api/runs/{run_id}/artifacts/{path:path}", dependencies=[Depends(launch.require_json)]
    )
    def edit_artifact(run_id: str, path: str, req: Text) -> Text:
        editing()
        try:
            stores.write_markdown(run_id, path, req.text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return req

    @app.get("/api/runs/{run_id}/views")
    def views(run_id: str) -> list[RunView]:
        return stores.list_views(run_id)

    @app.get("/api/runs/{run_id}/features")
    def feature_list(run_id: str) -> list[int]:
        return stores.list_features(run_id)

    @app.get("/api/runs/{run_id}/features/{feature}")
    def feature(run_id: str, feature: int) -> FeatureDashboard:
        return stores.get_feature(run_id, feature)

    @app.get("/api/runs/{run_id}/labels")
    def labels(run_id: str) -> dict[str, Label]:
        return stores.get_labels(run_id)

    @app.post("/api/runs/{run_id}/labels/{sample_id}", dependencies=[Depends(launch.require_json)])
    def label(run_id: str, sample_id: str, req: LabelRequest) -> dict[str, Label]:
        if not launching:
            raise HTTPException(403, "labelling is off: this server was started with --expose")
        try:
            return stores.set_label(run_id, sample_id, req.label)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/runs/{run_id}/agreement")
    def agreement(run_id: str) -> Agreement:
        try:
            return stores.agreement(run_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/compare")
    def compare(a: str, b: str) -> Comparison:
        return stores.compare(a, b)

    @app.get("/api/vectors")
    def vectors() -> list[Direction]:
        return stores.list_vectors()

    @app.get("/api/graphs")
    def graph_list() -> list[Graph]:
        return stores.list_graphs()

    @app.get("/api/experiments")
    def experiments() -> list[Experiment]:
        return stores.list_experiments()

    @app.get("/api/experiments/{name}/readme")
    def readme(name: str) -> Text:
        return Text(text=stores.read_readme(name))

    @app.put("/api/experiments/{name}/readme", dependencies=[Depends(launch.require_json)])
    def edit_readme(name: str, req: Text) -> Text:
        editing()
        try:
            stores.write_readme(name, req.text)
        except stores.BadExperiment as exc:  # the edit's fault, not the store's
            raise HTTPException(400, str(exc)) from exc
        return req

    @app.get("/api/experiments/{name}")
    def experiment(name: str) -> ExperimentDetail:
        return stores.get_experiment(name)

    app.include_router(playground.router(switchable=launching))
    app.include_router(launch.router(launching))
    graphs.mount(app)
    inspect_view.mount(app)

    if web_dir is not None and not web_dir.is_dir():
        print(f"no UI at {web_dir}: the API only (build the UI with just web-build)")
    elif web_dir is not None:
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
