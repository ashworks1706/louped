"""The FastAPI app: the API under /api, Inspect View at /inspect, circuit-tracer's graph viewer at
/circuit, and the built UI at / when there is one.

The server owns no database. Every route reads a store another tool already writes (MLflow,
Inspect logs, artifact files, experiments/), so deleting the server loses nothing. The one thing
it writes itself is a person's picks: labels on a judge run's pairs and blind A/B picks, plain
JSON under <home>/labels and <home>/ab. The
launch routes start louped's own commands as jobs, whose runs land in those same stores.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from louped import __version__, stores
from louped import reports as reporting
from louped import sources as library
from louped.check import Issue, check
from louped.core import Direction, cohorts, documents, home
from louped.core.judges import Judge, find_judges, write_judge
from louped.core.paths import experiments_dir, inside
from louped.server import graphs, hub, inspect_view, launch, playground, plugins, serving, ui
from louped.stores import ab, boards, gates
from louped.stores import experiments as experiment_store
from louped.stores import projects as project_store
from louped.stores.catalog import EvalTask, eval_tasks
from louped.stores.labels import Label
from louped.stores.mlflow_runs import Unreachable
from louped.stores.runs import read_artifact
from louped.stores.trace import run_code
from louped.stores.training_sets import (
    SetPairs,
    TrainingSet,
    list_training_sets,
    training_set_pairs,
)
from louped.stores.types import (
    AbResult,
    AbSession,
    Agreement,
    Axis,
    BoardView,
    CircuitGraph,
    CircuitPins,
    Comparison,
    Experiment,
    ExperimentDetail,
    FeatureDashboard,
    Graph,
    HeatmapView,
    Project,
    ProjectDetail,
    ProjectMeta,
    RunDetail,
    RunSummary,
    RunView,
    SampleDetail,
    SampleSummary,
    Trace,
    View,
)
from louped.sync import configured

#: Where the UI's dev server runs; allowed to call the API during development only.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

#: The Host headers answered by default: this machine only, so a page on another site cannot
#: reach the API through a rebound DNS name.
LOOPBACK = ["localhost", "127.0.0.1", "::1", "[::1]"]


class JudgeRequest(BaseModel):
    criterion: str = Field(min_length=1)
    prompt: str | None = None
    model: str | None = None
    about: str | None = None


class AbPickRequest(BaseModel):
    a: str
    b: str
    sample: str
    side: Literal["left", "right", "tie"] | None


class LabelRequest(BaseModel):
    #: The person's pick for the pair, or null to clear it.
    label: Label | None


class CohortQuery(BaseModel):
    """Which items to read each condition on (every item when ids is null), from which folder of
    the run's records, on which field, against which condition; the Items tab's defaults when
    unset."""

    ids: list[str] | None = Field(None, max_length=100_000)
    folder: str | None = None
    field: str | None = None
    reference: str | None = None


class Text(BaseModel):
    """A Markdown file's text."""

    text: str


class NewProject(ProjectMeta):
    #: Its folder's name under projects/: lowercase letters, digits and -.
    name: str


class NewExperiment(BaseModel):
    #: Its folder's name under experiments/: lowercase letters, digits and -.
    name: str
    domain: str
    #: The project it starts in; it must have its README.
    project: str | None = None


class ProjectChoice(BaseModel):
    #: The project to put the experiment in; null takes it out of its project.
    project: str | None


class DomainInfo(BaseModel):
    """A domain an experiment can be filed under, from louped.toml or louped's own."""

    key: str
    axis: Axis
    title: str


class SourceRequest(BaseModel):
    #: A file on this machine or an https URL (an arXiv page, a shared Google Doc, a file).
    location: str
    key: str | None = None
    title: str | None = None


class FigureRequest(BaseModel):
    #: The figure: run:<id>/views/<name>.json or experiment:<name>/views/<name>.json.
    ref: str
    format: reporting.Format = "svg"
    #: The file's name in reports/figures/; from the ref when empty.
    name: str | None = None
    #: Write over a file of the same name; without it, 409.
    replace: bool = False


class PreviewRequest(BaseModel):
    #: A figure as add_view takes one, not saved; checked first.
    view: dict[str, Any] | None = None
    #: A saved figure: run:<id>/views/<name>.json or experiment:<name>/views/<name>.json.
    ref: str | None = None


class PinRequest(BaseModel):
    key: str
    page: int
    #: The words as they stand on the page.
    quote: str
    note: str | None = None
    links: list[str] = []


class SourcePage(BaseModel):
    key: str
    page: int
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
    source checkout's apps/web/out, rebuilt first when its sources are newer. Says which, or that
    there is none and the API runs alone."""
    if given is not None:
        return given
    package = Path(__file__).resolve().parents[1]
    checkout = package.parents[1] / "apps" / "web"
    for found in (package / "web", checkout / "out"):
        if (found / "index.html").is_file():
            if found.parent == checkout:  # a release's build matches its code; a checkout's may not
                serving.current_ui(checkout)
            print(f"UI: {found}")
            return found
    print("no UI found: the API only. In a checkout, build it with `just web-build`.")
    return None


#: The app's theme, for a page it shows in a frame.
Theme = Literal["light", "dark"]


def _notebook_page(html: str) -> HTMLResponse:
    """A notebook's page, sandboxed by its own header too: a notebook from the web can carry any
    script in its outputs, and opened outside the app's frame it still runs none."""
    return HTMLResponse(html, headers={"Content-Security-Policy": "sandbox"})


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

    @app.exception_handler(Unreachable)
    async def unreachable(_: Request, exc: Unreachable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(stores.BadExperiment)
    async def bad_experiment(_: Request, exc: stores.BadExperiment) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=500)

    editing = launch.editing_guard(launching)

    @app.get("/api/health")
    def health() -> Health:
        return Health(status="ok", version=__version__, home=str(home()), launching=launching,
                      remote=configured() if launching else None)  # fmt: skip

    @app.get("/api/runs")
    def runs() -> list[RunSummary]:
        return stores.list_runs()

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> RunDetail:
        found = stores.get_run(run_id)
        return found.model_copy(update={"code": run_code(found)})

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
        if (kept := stores.remote_artifact(run_id, path)) is not None:  # big: left in the remote
            return FileResponse(kept, media_type=media)
        return Response(read_artifact(run_id, path), media_type=media)

    @app.get("/api/runs/{run_id}/notebook/{path:path}")
    def run_notebook(run_id: str, path: str, theme: Theme = "light") -> HTMLResponse:
        """A notebook the run logged, as a page, for a frame that runs no scripts."""
        if ".." in Path(path).parts or not path.endswith(".ipynb"):
            raise HTTPException(400, "not a notebook's path")
        try:
            html = documents.notebook_html(read_artifact(run_id, path), dark=theme == "dark")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _notebook_page(html)

    @app.put(
        "/api/runs/{run_id}/artifacts/{path:path}", dependencies=[Depends(launch.require_json)]
    )
    def edit_artifact(run_id: str, path: str, req: Text) -> Text:
        editing()
        try:
            stores.write_text(run_id, path, req.text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return req

    @app.delete("/api/runs/{run_id}", dependencies=[Depends(launch.require_json)])
    def delete_run(run_id: str) -> None:
        editing()
        try:
            stores.delete_run(run_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/runs/{run_id}/cohort", dependencies=[Depends(launch.require_json)])
    def run_cohort(run_id: str, req: CohortQuery) -> stores.CohortStats:
        """Each condition of a run's per-item records on some of its items, and each one's
        paired difference from the reference with a 95% interval."""
        try:
            return stores.cohort(run_id, req.ids, req.folder, req.field, req.reference)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sources")
    def sources() -> list[library.Source]:
        """The project's sources/: papers, docs, slides and notebooks, by key."""
        return library.list_sources()

    @app.get("/api/sources/search")
    def search_sources(q: str, limit: int = 10) -> list[library.Hit]:
        """The source pages holding every word of q, best first."""
        return library.search(q, min(max(limit, 1), 50))

    @app.get("/api/sources/{key}/pages/{page}")
    def source_page(key: str, page: int) -> SourcePage:
        try:
            return SourcePage(key=key, page=page, text=library.page_text(key, page))
        except KeyError as exc:
            raise HTTPException(404, exc.args[0]) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/sources/{key}/file")
    def source_file(key: str) -> FileResponse:
        """A source's file as it was kept, for the app's viewer."""
        try:
            path = library.source_file(key)
        except KeyError as exc:
            raise HTTPException(404, exc.args[0]) from exc
        except ValueError as exc:  # an index entry naming a file outside sources/
            raise HTTPException(400, str(exc)) from exc
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=kind, headers={"Cache-Control": "no-cache"})

    @app.get("/api/sources/{key}/notebook")
    def source_notebook(key: str, theme: Theme = "light") -> HTMLResponse:
        """A notebook source as a page, for a frame that runs no scripts."""
        try:
            path = library.source_file(key)
        except KeyError as exc:
            raise HTTPException(404, exc.args[0]) from exc
        except ValueError as exc:  # an index entry naming a file outside sources/
            raise HTTPException(400, str(exc)) from exc
        if path.suffix != ".ipynb":
            raise HTTPException(400, f"{key} is not a notebook")
        try:
            return _notebook_page(documents.notebook_html(path, dark=theme == "dark"))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/pins")
    def pins(key: str | None = None) -> list[library.Pin]:
        """The pinned passages of one source, or of all."""
        return library.pins(key)

    @app.post("/api/pins", dependencies=[Depends(launch.require_json)])
    def add_pin(req: PinRequest) -> library.Pin:
        """Pin a quote on a page of a source: refused unless the words are on that page."""
        editing()
        try:
            return library.add_pin(req.key, req.page, req.quote, req.note, req.links)
        except KeyError as exc:
            raise HTTPException(404, exc.args[0]) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/pins/{pin_id}", dependencies=[Depends(launch.require_json)])
    def delete_pin(pin_id: str) -> None:
        editing()
        try:
            library.delete_pin(pin_id)
        except KeyError as exc:
            raise HTTPException(404, exc.args[0]) from exc

    @app.post("/api/sources", dependencies=[Depends(launch.require_json)])
    def add_source(req: SourceRequest) -> library.Source:
        """A file or URL added to sources/, its text to the search index."""
        editing()
        try:
            if library.is_url(req.location):
                return library.add_url(req.location, req.key, req.title)
            # a file must be inside the project: over HTTP the app never reads elsewhere
            path = inside(experiments_dir().parent, req.location)
            return library.add_file(path, req.key, req.title)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"could not fetch {req.location}: {exc}") from exc

    @app.get("/api/reports")
    def report_list() -> list[reporting.Report]:
        """Every file in reports/ the app shows; 400 naming an exported figure's broken refs
        file."""
        try:
            return reporting.list_reports()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/live")
    def live(ref: Annotated[list[str], Query(max_length=500)]) -> list[reporting.Live]:
        """Live refs in Markdown, each as written between its braces (run:<id> <metric>
        [:<format>], or a figure's ref): a metric's value or the figure, else why not."""
        return reporting.resolve(ref)

    def _report_error(exc: Exception) -> HTTPException:
        if isinstance(exc, FileNotFoundError):
            return HTTPException(404, str(exc))
        if isinstance(exc, reporting.MissingTool):
            return HTTPException(501, str(exc))
        return HTTPException(400, str(exc))

    @app.get("/api/reports/file")
    def report_file(path: str, download: bool = False) -> FileResponse:
        """A file in reports/ as it is; with download, as a file to save."""
        try:
            file = reporting.report_file(path)
            return FileResponse(file, filename=file.name if download else None)
        except (ValueError, FileNotFoundError) as exc:
            raise _report_error(exc) from exc

    @app.get("/api/reports/outline")
    def report_outline(path: str) -> list[str]:
        """A deck's text slide by slide, a document's paragraph by paragraph."""
        try:
            return reporting.outline(path)
        except (ValueError, FileNotFoundError) as exc:
            raise _report_error(exc) from exc

    @app.get("/api/reports/preview")
    def report_preview(path: str) -> FileResponse:
        """A deck or document as a PDF drawn by LibreOffice; 501 when it is not installed."""
        try:
            return FileResponse(reporting.preview_pdf(path), media_type="application/pdf")
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            raise _report_error(exc) from exc

    @app.post("/api/reports/figures", dependencies=[Depends(launch.require_json)])
    def export_figure(req: FigureRequest) -> reporting.Report:
        """A run's or experiment's figure exported to reports/figures/ with its ref and trace."""
        editing()
        try:
            return reporting.export_figure(req.ref, req.format, req.name, req.replace)
        except stores.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise _report_error(exc) from exc

    @app.post(
        "/api/views/preview",
        dependencies=[Depends(launch.require_json)],
        response_class=Response,
        responses={200: {"content": {"image/png": {}}}},
    )
    def preview_view(req: PreviewRequest) -> Response:
        """A vega or plotly figure drawn as a PNG, unsaved or at its ref: 400 with what is wrong
        in a view that does not check, 501 when Plotly finds no Chrome. Off with --expose, like
        export: it draws any spec it is sent."""
        editing()
        try:
            return Response(reporting.preview(req.view, req.ref), media_type="image/png")
        except stores.NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise _report_error(exc) from exc

    @app.get("/api/check")
    def grounded(path: str | None = None) -> list[Issue]:
        """What in the project's write-ups is not grounded (louped check): a file or folder in
        the project, or every .md, .pptx and .docx under experiments/ and reports/."""
        try:
            where = [inside(experiments_dir().parent, path)] if path else None
            return check(where)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/trace")
    def trace(ref: str) -> Trace:
        """Where a ref's evidence comes from: a figure's mark down to the script that made the
        figure, the item's rows in every file, and the run with its commit."""
        try:
            return stores.trace(ref)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/runs/{run_id}/views")
    def views(run_id: str) -> list[RunView]:
        return stores.list_views(run_id)

    @app.put("/api/runs/{run_id}/views/{name}", dependencies=[Depends(launch.require_json)])
    def add_view(run_id: str, name: str, req: View) -> RunView:
        """A figure added to a run after it ran: views/<name>.json, replacing one of that name.
        Only an MLflow run (an analysis or training) takes one."""
        editing()
        try:
            added = stores.add_view(run_id, name, req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if added is None:
            raise HTTPException(
                404,
                f"no analysis or training run {run_id}: an eval run's "
                "figures go on its experiment's page",
            )
        return added

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

    @app.get("/api/ab")
    def ab_session(a: str, b: str) -> AbSession:
        """Two eval runs' shared samples as blind pairs, with the person's picks so far."""
        if not launching:
            raise HTTPException(403, "blind A/B is off: this server was started with --expose")
        try:
            return ab.session(a, b)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/ab/pick", dependencies=[Depends(launch.require_json)])
    def ab_pick(req: AbPickRequest) -> AbSession:
        """The person's pick of one pair, by the side they saw; null clears it."""
        if not launching:
            raise HTTPException(403, "blind A/B is off: this server was started with --expose")
        try:
            return ab.set_pick(req.a, req.b, req.sample, req.side)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/ab/result")
    def ab_result(a: str, b: str) -> AbResult:
        """B's win rate by the person's blind picks, with each judge run's agreement."""
        try:
            return ab.result(a, b)
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

    @app.get("/api/vectors/similarity")
    def vector_similarity(model: str) -> HeatmapView:
        """How alike one model's saved directions are: the cosine of each pair, as a figure."""
        from louped.vectors import similarity

        names = sorted(v.name for v in stores.list_vectors() if v.model == model)
        if len(names) < 2:
            raise HTTPException(404, f"{model} has fewer than two saved vectors")
        cos = similarity(names)
        return HeatmapView(
            kind="heatmap",
            title="How alike they are",
            x=names,
            y=names,
            x_label="vector",
            y_label="vector",
            z=[[c or 0.0 for c in row] for row in cos],
            labels=[["—" if c is None else f"{c:.2f}" for c in row] for row in cos],
            about="The cosine between each pair of directions: 1 the same direction, 0 unrelated, "
            "-1 opposite. Two vectors near 1 steer the same thing; a new one near 0 to all the "
            "others is new. — marks vectors of different sizes.",
        )

    @app.get("/api/training-sets")
    def training_sets() -> list[TrainingSet]:
        """The training sets louped knows, each with its flag counts and warnings."""
        return list_training_sets()

    @app.get("/api/training-sets/pairs")
    def training_set(path: str) -> SetPairs:
        """One known set's pairs side by side, flagged ones first."""
        try:
            return training_set_pairs(path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/graphs")
    def graph_list() -> list[Graph]:
        return stores.list_graphs()

    @app.get("/api/graphs/{slug}")
    def graph(slug: str) -> CircuitGraph:
        """One graph with each node's and edge's share of the influence on the logits."""
        try:
            return stores.get_graph(slug)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/api/graphs/{slug}/pins", dependencies=[Depends(launch.require_json)])
    def graph_pins(slug: str, req: CircuitPins) -> CircuitPins:
        """Keeps the pinned nodes and groups in the graph file, as circuit-tracer's viewer does."""
        editing()
        try:
            return stores.save_pins(slug, req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/experiments")
    def experiments() -> list[Experiment]:
        return stores.list_experiments()

    @app.post("/api/experiments", dependencies=[Depends(launch.require_json)])
    def new_experiment(req: NewExperiment) -> ExperimentDetail:
        """experiments/<name>/ with its README and run.py, active, in a project when given."""
        editing()
        try:
            experiment_store.scaffold(req.name, req.domain, req.project)
        except stores.BadExperiment as exc:
            raise HTTPException(400, str(exc)) from exc
        return stores.get_experiment(req.name)

    @app.put("/api/experiments/{name}/project", dependencies=[Depends(launch.require_json)])
    def move_experiment(name: str, req: ProjectChoice) -> ExperimentDetail:
        """Rewrites only the project: line of the experiment's front matter; its folder stays."""
        editing()
        try:
            experiment_store.set_project(name, req.project)
        except stores.BadExperiment as exc:
            raise HTTPException(400, str(exc)) from exc
        return stores.get_experiment(name)

    @app.get("/api/domains")
    def domain_list() -> list[DomainInfo]:
        """The domains an experiment can be filed under, in the Experiments page's order."""
        return [DomainInfo(key=k, axis=axis, title=title)
                for k, (axis, title) in experiment_store.domains().items()]  # fmt: skip

    @app.get("/api/projects")
    def projects() -> list[Project]:
        """Every project under projects/, then any that experiments name with no README."""
        return project_store.list_projects()

    @app.post("/api/projects", dependencies=[Depends(launch.require_json)])
    def new_project(req: NewProject) -> ProjectDetail:
        """Writes projects/<name>/README.md: the front matter, then sections to fill in."""
        editing()
        meta = ProjectMeta.model_validate(req.model_dump(exclude={"name"}))
        try:
            project_store.create(req.name, meta)
        except stores.BadExperiment as exc:
            raise HTTPException(400, str(exc)) from exc
        return project_store.get_project(req.name)

    @app.get("/api/projects/{name}")
    def project(name: str) -> ProjectDetail:
        return project_store.get_project(name)

    @app.get("/api/projects/{name}/readme")
    def project_readme(name: str) -> Text:
        return Text(text=project_store.read_readme(name))

    @app.put("/api/projects/{name}/readme", dependencies=[Depends(launch.require_json)])
    def edit_project_readme(name: str, req: Text) -> Text:
        editing()
        try:
            project_store.write_readme(name, req.text)
        except stores.BadExperiment as exc:  # the edit's fault, not the store's
            raise HTTPException(400, str(exc)) from exc
        return req

    @app.put("/api/projects/{name}/meta", dependencies=[Depends(launch.require_json)])
    def edit_project_meta(name: str, req: ProjectMeta) -> ProjectDetail:
        """Replaces the README's front matter and keeps the text under it."""
        editing()
        project_store.set_meta(name, req)
        return project_store.get_project(name)

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

    @app.delete("/api/experiments/{name}", dependencies=[Depends(launch.require_json)])
    def delete_experiment(name: str) -> Text:
        """Moves its folder to <home>/trash/experiments; says where."""
        editing()
        return Text(text=str(stores.delete_experiment(name)))

    @app.get("/api/experiments/{name}/cohorts")
    def cohort_list(name: str) -> list[cohorts.Saved]:
        stores.get_experiment(name)  # NotFound for a name that is no experiment
        try:
            return cohorts.listed(name)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.put(
        "/api/experiments/{name}/cohorts/{cohort}", dependencies=[Depends(launch.require_json)]
    )
    def save_cohort(name: str, cohort: str, req: cohorts.Cohort) -> cohorts.Saved:
        """Writes experiments/<name>/cohorts/<cohort>.json, replacing one of that name."""
        editing()
        try:
            return cohorts.save(name, cohort, req)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/experiments/{name}/views")
    def experiment_views(name: str) -> list[RunView]:
        """The experiment's own figures, under experiments/<name>/views/."""
        try:
            return stores.experiment_views(name)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.put("/api/experiments/{name}/views/{view}", dependencies=[Depends(launch.require_json)])
    def save_experiment_view(name: str, view: str, req: View) -> RunView:
        """Writes experiments/<name>/views/<view>.json, replacing one of that name."""
        editing()
        try:
            return stores.save_experiment_view(name, view, req)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/board/table")
    def board_table(ref: str) -> boards.Table:
        """The rows a board's table reads: run:<id>/<path>, experiment:<name>/<path>,
        metrics:<run id>, runs: or runs:<experiment> (louped.stores.boards)."""
        try:
            return boards.read_table(ref)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/board/check", dependencies=[Depends(launch.require_json)])
    def board_check(req: View) -> boards.BoardCheck:
        """A board's tables read and its panels tried, before it is shown: what the agent fixes."""
        if not isinstance(req, BoardView):
            raise HTTPException(400, f"a {req.kind} figure is not a board")
        return boards.check(req)

    @app.get("/api/boards")
    def list_boards() -> list[boards.BoardPage]:
        """The boards shown as pages of their own: boards/<name>.json at the project's root."""
        return boards.list_boards()

    @app.get("/api/boards/{name}")
    def get_board(name: str) -> BoardView:
        try:
            return boards.get_board(name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/api/boards/{name}", dependencies=[Depends(launch.require_json)])
    def save_board(name: str, req: View) -> boards.BoardPage:
        """Writes boards/<name>.json, replacing one of that name: a page in the sidebar."""
        editing()
        if not isinstance(req, BoardView):
            raise HTTPException(400, f"a page is a board; this is a {req.kind} figure")
        try:
            return boards.save_board(name, req)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/judges")
    def list_judges() -> list[Judge]:
        """louped's judge and the project's judges/<name>.py, for Compare and Launch."""
        try:
            return find_judges()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/api/judges/{name}", dependencies=[Depends(launch.require_json)])
    def save_judge(name: str, req: JudgeRequest) -> Judge:
        """Writes judges/<name>.py, replacing one of that name."""
        editing()
        try:
            return write_judge(name, req.criterion, req.prompt, req.model, req.about)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/evals")
    def list_eval_tasks() -> list[EvalTask]:
        """Every task Launch's inspect eval can run: the project's, then inspect_evals'."""
        try:
            return eval_tasks()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/experiments/{name}")
    def experiment(name: str) -> ExperimentDetail:
        found = stores.get_experiment(name)
        return found.model_copy(update={"gate": gates.status(name)})

    app.include_router(playground.router(switchable=launching))
    jobs = launch.Jobs() if launching else None
    app.include_router(launch.router(jobs))
    app.include_router(hub.router(jobs))
    pages: dict[str, list[str]] = {}  # the plugins' pages, once plugins.mount has served them
    app.include_router(ui.router(launching, pages))
    # louped's look and helpers for plugin pages (louped.server.ui, plugins.mdx)
    app.mount("/kit", StaticFiles(directory=Path(__file__).parent / "kit"), name="kit")
    plugins.mount(app, launching, pages)
    graphs.mount(app)
    inspect_view.mount(app)

    if web_dir is not None and not web_dir.is_dir():
        print(f"no UI at {web_dir}: the API only (build the UI with just web-build)")
    elif web_dir is not None:
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
