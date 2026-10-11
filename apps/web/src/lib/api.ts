import type { Query } from "@tanstack/react-query";

import type { components } from "@/lib/api-types";

/** The API origin: set in development, the same origin when served by `louped serve`. */
export const API = process.env.NEXT_PUBLIC_LOUPED_API ?? "";

type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type RunSummary = Schemas["RunSummary"];
export type RunDetail = Schemas["RunDetail"];
export type SampleSummary = Schemas["SampleSummary"];
export type SampleDetail = Schemas["SampleDetail"];
export type ModelInput = Schemas["ModelInput"];
export type Experiment = Schemas["Experiment"];
export type ExperimentDetail = Schemas["ExperimentDetail"];
type RunView = Schemas["RunView"];
export type HeatmapView = Schemas["HeatmapView"];
export type LineView = Schemas["LineView"];
export type TableView = Schemas["TableView"];
export type ScatterView = Schemas["ScatterView"];
export type TokensView = Schemas["TokensView"];
export type VegaView = Schemas["VegaView"];
export type PlotlyView = Schemas["PlotlyView"];
export type BoardView = Schemas["BoardView"];
export type BoardPanel = Schemas["BoardPanel"];
export type BoardControl = Schemas["BoardControl"];
export type BoardFilter = Schemas["BoardFilter"];
export type BoardTable = Schemas["Table"];
export type BoardPage = Schemas["BoardPage"];
export type Trace = Schemas["Trace"];
export type Code = Schemas["Code"];
export type Source = Schemas["Source"];
export type SourceHit = Schemas["Hit"];
export type Pin = Schemas["Pin"];
export type Report = Schemas["Report"];
export type Live = Schemas["Live"];
export type SourcePage = Schemas["SourcePage"];
export type Pushed = Schemas["Pushed"];
export type RemoteState = Schemas["RemoteState"];
export type HubAccount = Schemas["Account"];
export type HubHit = Schemas["HubHit"];
export type HubDetail = Schemas["HubDetail"];
export type HubAdded = Schemas["HubAdded"];
export type HubKind = HubHit["kind"];
export type HubSort = "downloads" | "likes" | "recent";
export type PluginInfo = Schemas["PluginInfo"];
export type View = RunView["view"];
export type Direction = Schemas["Direction"];
export type TrainingSet = Schemas["TrainingSet"];
export type SetPairs = Schemas["SetPairs"];
export type Pair = Schemas["Pair"];
type Graph = Schemas["Graph"];
export type CircuitGraph = Schemas["CircuitGraph"];
export type CircuitNode = Schemas["CircuitNode"];
export type CircuitLink = Schemas["CircuitLink"];
export type CircuitPins = Schemas["CircuitPins"];
type Comparison = Schemas["Comparison"];
export type PairedScore = Schemas["PairedScore"];
export type PlaygroundInfo = Schemas["PlaygroundInfo"];
type GenerateRequest = Schemas["GenerateRequest"];
type InspectRequest = Schemas["InspectRequest"];
type InspectResponse = Schemas["InspectResponse"];
export type FeatureDashboard = Schemas["FeatureDashboard"];
export type Launchable = Schemas["Launchable"];
export type LaunchOption = Schemas["Option"];
export type Judge = Schemas["Judge"];
export type AbSession = Schemas["AbSession"];
export type AbResult = Schemas["AbResult"];
export type EvalTask = Schemas["EvalTask"];
export type LaunchRequest = Schemas["LaunchRequest"];
export type Job = Schemas["Job"];
export type Target = Schemas["Target"];
/** The server fills in any target field left out with its default. */
export type ExportRequest = LaunchRequest & {
  target: Partial<Target> & Pick<Target, "provider">;
};
/** A launch sent to a cluster louped.toml names, after an earlier job there or not. */
export type SubmitRequest = ExportRequest & { cluster: string; after?: string | null };
export type Cluster = Schemas["ClusterInfo"];
export type GateStatus = Schemas["GateStatus"];
export type Imported = Schemas["Imported"];
export type Agreement = Schemas["Agreement"];
export type Label = "a" | "b" | "tie";
type JobDetail = Schemas["JobDetail"];
export type Block = Schemas["Block"];
export type UiPage = Schemas["Page"];
export type Theme = Schemas["Theme"];
export type Selection = Schemas["Selection"];
export type Picked = Schemas["Picked"];
export type Picks = Schemas["Picks"];
export type PartRule = Schemas["PartRule"];
export type Cue = Schemas["Cue"];
export type Cues = Schemas["Cues"];
export type CohortStats = Schemas["CohortStats"];
type SavedCohort = Schemas["Saved"];
type CohortQuery = Schemas["CohortQuery"];
type Cohort = Schemas["Cohort"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** A page from `louped publish`: its API answers are files, api/<key>.json (see publish.py). */
export const isSnapshot = () =>
  typeof document !== "undefined" &&
  document.querySelector('meta[name="louped-snapshot"]') !== null;

/** Longer keys are hashed, as publish.py names their files. */
const MAX_KEY = 200;

async function url(path: string): Promise<string> {
  if (!isSnapshot()) return `${API}/api${path}`;
  let key = encodeURIComponent(path).replaceAll("%", ",");
  if (key.length > MAX_KEY) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key));
    key = "h-" + [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  return `${API}/api/${key}.json`;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(await url(path), { signal });
  if (!res.ok) throw new ApiError(res.status, await detail(res, path));
  return res.json() as Promise<T>;
}

/** The server's own error message, else the status and path. */
async function detail(res: Response, path: string): Promise<string> {
  const body = await res
    .json()
    .then((b: { detail?: unknown }) => b.detail)
    .catch(() => null);
  return typeof body === "string" ? body : `${res.status} ${path}`;
}

async function send(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`${API}/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res, path));
  return res;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}/api${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res, path));
  return res.json() as Promise<T>;
}

/** An experiment's README as written, front matter and all. */
export const readme = (name: string) =>
  get<{ text: string }>(`/experiments/${encodeURIComponent(name)}/readme`).then((r) => r.text);
export const saveReadme = (name: string, text: string) =>
  put(`/experiments/${encodeURIComponent(name)}/readme`, { text });
/** Replaces a Markdown file a run logged. */
export const saveArtifact = (run: string, path: string, text: string) =>
  put(
    `/runs/${encodeURIComponent(run)}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`,
    { text },
  );

async function del(path: string): Promise<void> {
  const res = await fetch(`${API}/api${path}`, {
    method: "DELETE",
    headers: { "content-type": "application/json" },
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res, path));
}

/** Moves an experiment's folder to the trash; its runs stay. */
export const deleteExperiment = (name: string) => del(`/experiments/${encodeURIComponent(name)}`);
/** Deletes a run that has ended: an eval's log goes to the trash, an MLflow run is marked deleted. */
export const deleteRun = (id: string) => del(`/runs/${encodeURIComponent(id)}`);
/** Moves a job that has ended, with its log, to the trash; its runs stay. */
/** Each condition of a run's items on some of them, and its paired difference from the
 * reference. */
export const cohortStats = (run: string, body: CohortQuery) =>
  post<CohortStats>(`/runs/${encodeURIComponent(run)}/cohort`, body);
/** Saves items as experiments/<experiment>/cohorts/<name>.json. */
export const saveCohort = (experiment: string, name: string, cohort: Omit<Cohort, "created">) =>
  put<SavedCohort>(
    `/experiments/${encodeURIComponent(experiment)}/cohorts/${encodeURIComponent(name)}`,
    cohort,
  );
/** Keeps a graph's pinned nodes and groups in its file, where circuit-tracer's viewer reads them. */
export const saveGraphPins = (slug: string, pins: CircuitPins) =>
  put<CircuitPins>(`/graphs/${encodeURIComponent(slug)}/pins`, pins);
export const deleteJob = (id: string) => del(`/launch/jobs/${encodeURIComponent(id)}`);

async function post<T>(path: string, body: unknown): Promise<T> {
  return (await send(path, body)).json() as Promise<T>;
}

/** Streams a reply: onText gets each piece as the model writes it. Abort the signal to stop. */
export async function generate(
  req: GenerateRequest,
  onText: (text: string) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await send("/playground/generate", req, signal);
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  for (let r = await reader.read(); !r.done; r = await reader.read()) onText(r.value);
}

export const inspect = (req: InspectRequest) => post<InspectResponse>("/playground/inspect", req);
export const patch = (req: Schemas["PatchRequest"]) =>
  post<InspectResponse>("/playground/patch", req);
export const dose = (req: Schemas["DoseRequest"]) => post<InspectResponse>("/playground/dose", req);
export const speed = (req: Schemas["SpeedRequest"]) =>
  post<InspectResponse>("/playground/speed", req);

export const health = (signal?: AbortSignal) => get<Health>("/health", signal);

export const launch = (req: LaunchRequest) => post<Job>("/launch", req);

/** Downloads what runs req on another machine; note says what it is and how results come back. */
export async function exportJob(req: ExportRequest): Promise<{ name: string; note: string }> {
  const res = await send("/launch/export", req);
  const name =
    /filename="?([^";]+)"?/.exec(res.headers.get("content-disposition") ?? "")?.[1] ??
    "louped-job.tar.gz";
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
  return { name, note: res.headers.get("x-louped-note") ?? "" };
}

/** Sends a launch to a cluster over ssh and starts it there; louped follows it to its result. */
export const submitJob = (req: SubmitRequest) => post<Job>("/launch/submit", req);

/** Hands the person's agent the parts they picked (ui_selection). */
export const pick = (s: Selection) => post<Picks>("/ui/selection", s);
/** What the person's agent asked the app to show them, after the last one the app has. */
export const cuesAfter = (after: number) => get<Cues>(`/ui/show?after=${after}`);
/** Tells the agent the app showed a cue, and which of its parts were not on the page; or that a
 * newer cue came first. */
export const cueSeen = (id: number, missing: string[], superseded = false) =>
  post<Cue>(`/ui/show/${id}/seen`, { missing, superseded });

/** Pushes this louped's new runs to the project's remote. */
export const pushRuns = () => post<Pushed>("/launch/push", {});
/** Adds the runs in the remote this louped has not pulled. */
export const pullRuns = () => post<Imported[]>("/launch/pull", {});
/** Sets the project's remote (empty: a private HF bucket of your own), keeping a token if given. */
export const connectRemote = (body: Schemas["Connect"]) =>
  post<RemoteState>("/launch/remote", body);

/** Adds a result archive from another machine to this louped. */
export async function importResult(file: File): Promise<Imported> {
  const res = await fetch(`${API}/api/launch/import`, {
    method: "POST",
    headers: { "content-type": "application/gzip" },
    body: file,
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res, "/launch/import"));
  return res.json() as Promise<Imported>;
}
export const setLabel = (run: string, sample: string, label: Label | null) =>
  post<Record<string, Label>>(
    `/runs/${encodeURIComponent(run)}/labels/${encodeURIComponent(sample)}`,
    { label },
  );
/** A source's file as kept, for the viewer. */
export const sourceFile = (key: string) => `${API}/api/sources/${encodeURIComponent(key)}/file`;
/** A notebook source as the page the API draws it as. */
export const sourceNotebook = (key: string) =>
  `${API}/api/sources/${encodeURIComponent(key)}/notebook`;
/** Checks a Hugging Face token and keeps it where huggingface_hub keeps it. */
export const saveHubToken = (token: string) => post<HubAccount>("/hub/token", { token });
/** Lists a model, embedding model or dataset in louped.toml (and downloads it as a job), or
 * keeps a paper as a source. */
export const hubAdd = (body: Schemas["AddRequest"]) => post<Schemas["AddResult"]>("/hub/add", body);
export const addSource = (body: Schemas["SourceRequest"]) => post<Source>("/sources", body);
export const addPin = (body: Schemas["PinRequest"]) => post<Pin>("/pins", body);
export const deletePin = (id: string) => del(`/pins/${encodeURIComponent(id)}`);
/** A file in reports/ as it is. */
export const reportFile = (path: string, download = false) =>
  `${API}/api/reports/file?path=${encodeURIComponent(path)}${download ? "&download=true" : ""}`;
/** A figure exported to reports/figures/, with its ref and trace beside it. */
export const exportFigure = (body: Schemas["FigureRequest"]) =>
  post<Report>("/reports/figures", body);
/** A blind pick of one pair by the side the person saw; null clears it. */
export const abPick = (body: Schemas["AbPickRequest"]) => post<AbSession>("/ab/pick", body);
/** What a Probe or Benchmark tool showed, kept as a run. */
export const saveResult = (req: Schemas["SaveRequest"]) =>
  post<Schemas["SavedResult"]>("/playground/save", req);
export const loadModel = (req: Schemas["LoadRequest"]) =>
  post<PlaygroundInfo>("/playground/load", req);
export const cancelJob = (id: string) =>
  post<Job>(`/launch/jobs/${encodeURIComponent(id)}/cancel`, {});

/** A run still writing (Inspect says started, MLflow running), or a job not yet ended: queued
 * here, or submitted to a cluster's scheduler. */
export const isLive = (status: string) =>
  status === "started" || status === "running" || status === "queued" || status === "submitted";

/** How often a page refetches a run that is still writing. */
const LIVE_MS = 3000;
/** How often a page rereads its layout while an agent may be changing it. */
const LAYOUT_MS = 2000;
const every = (live: boolean | undefined): number | false => (live ? LIVE_MS : false);

/** Query keys and fetchers, one per endpoint, so pages never build URLs by hand. Queries over a
 * live run poll until it ends. */
export const q = {
  /** The picks as the server keeps them: read says which version the agent last read. */
  picks: () => ({
    queryKey: ["picks"],
    queryFn: () => get<Picks | null>("/ui/selection"),
    refetchInterval: 2000,
  }),
  health: () => ({ queryKey: ["health"], queryFn: () => get<Health>("/health"), retry: false }),
  /** The project's plugins: none in a published dashboard, which has no answer for them. Polled,
   * so a plugin the agent adds shows without a reload. */
  plugins: () => ({
    queryKey: ["plugins"],
    queryFn: () => (isSnapshot() ? Promise.resolve([]) : get<PluginInfo[]>("/plugins")),
    retry: false,
    refetchInterval: () => (isSnapshot() ? false : 3000),
  }),
  runs: () => ({
    queryKey: ["runs"],
    queryFn: () => get<RunSummary[]>("/runs"),
    refetchInterval: (query: Query<RunSummary[]>) =>
      every(query.state.data?.some((r) => isLive(r.status))),
  }),
  run: (id: string) => ({
    queryKey: ["run", id],
    queryFn: () => get<RunDetail>(`/runs/${encodeURIComponent(id)}`),
    refetchInterval: (query: Query<RunDetail>) =>
      every(query.state.data && isLive(query.state.data.status)),
  }),
  samples: (id: string, live = false) => ({
    queryKey: ["samples", id],
    queryFn: () => get<SampleSummary[]>(`/runs/${encodeURIComponent(id)}/samples`),
    refetchInterval: every(live),
  }),
  sample: (id: string, sample: string, epoch = 1) => ({
    queryKey: ["sample", id, sample, epoch],
    queryFn: () =>
      get<SampleDetail>(
        `/runs/${encodeURIComponent(id)}/samples/${encodeURIComponent(sample)}?epoch=${epoch}`,
      ),
  }),
  labels: (id: string) => ({
    queryKey: ["labels", id],
    queryFn: () => get<Record<string, Label>>(`/runs/${encodeURIComponent(id)}/labels`),
  }),
  agreement: (id: string) => ({
    queryKey: ["agreement", id],
    queryFn: () => get<Agreement>(`/runs/${encodeURIComponent(id)}/agreement`),
  }),
  sources: () => ({
    queryKey: ["sources"],
    queryFn: () => get<Source[]>("/sources"),
  }),
  sourceSearch: (query: string) => ({
    queryKey: ["source-search", query],
    queryFn: () => get<SourceHit[]>(`/sources/search?q=${encodeURIComponent(query)}`),
  }),
  sourcePage: (key: string, page: number) => ({
    queryKey: ["source-page", key, page],
    queryFn: () => get<SourcePage>(`/sources/${encodeURIComponent(key)}/pages/${page}`),
  }),
  pins: (key?: string) => ({
    queryKey: ["pins", key ?? null],
    queryFn: () => get<Pin[]>(`/pins${key ? `?key=${encodeURIComponent(key)}` : ""}`),
  }),
  reports: () => ({
    queryKey: ["reports"],
    queryFn: () => get<Report[]>("/reports"),
  }),
  reportOutline: (path: string, modified: string) => ({
    queryKey: ["report-outline", path, modified],
    queryFn: () => get<string[]>(`/reports/outline?path=${encodeURIComponent(path)}`),
  }),
  /** A deck or document drawn as a PDF by LibreOffice: its bytes, or why it cannot be. */
  reportPreview: (path: string, modified: string) => ({
    queryKey: ["report-preview", path, modified],
    queryFn: async () => {
      const res = await fetch(`${API}/api/reports/preview?path=${encodeURIComponent(path)}`);
      if (!res.ok) throw new ApiError(res.status, await detail(res, path));
      return new Uint8Array(await res.arrayBuffer());
    },
    retry: false,
  }),
  /** Live refs in Markdown, each as written between its braces, resolved in one request. */
  live: (refs: string[]) => ({
    queryKey: ["live", refs],
    queryFn: () =>
      get<Live[]>(`/live?${refs.map((r) => `ref=${encodeURIComponent(r)}`).join("&")}`),
  }),
  trace: (ref: string) => ({
    queryKey: ["trace", ref],
    queryFn: () => get<Trace>(`/trace?ref=${encodeURIComponent(ref)}`),
  }),
  views: (id: string, live = false) => ({
    queryKey: ["views", id],
    queryFn: () => get<RunView[]>(`/runs/${encodeURIComponent(id)}/views`),
    refetchInterval: every(live),
  }),
  features: (run: string) => ({
    queryKey: ["features", run],
    queryFn: () => get<number[]>(`/runs/${encodeURIComponent(run)}/features`),
  }),
  feature: (run: string, feature: number) => ({
    queryKey: ["feature", run, feature],
    queryFn: () => get<FeatureDashboard>(`/runs/${encodeURIComponent(run)}/features/${feature}`),
  }),
  /** The Hugging Face account whose token is on this machine. */
  hubMe: () => ({
    queryKey: ["hub", "me"],
    queryFn: () => get<HubAccount>("/hub/me"),
    retry: false,
  }),
  hubSearch: (p: { kind: HubKind; q: string; task: string; library: string; sort: HubSort }) => ({
    queryKey: ["hub", "search", p],
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      get<HubHit[]>(`/hub/search?${new URLSearchParams({ ...p, limit: "30" })}`, signal),
    retry: false,
    staleTime: 60_000,
  }),
  hubInfo: (kind: HubKind, id: string) => ({
    queryKey: ["hub", "info", kind, id],
    queryFn: () => get<HubDetail>(`/hub/info?kind=${kind}&id=${encodeURIComponent(id)}`),
    retry: false,
    staleTime: 60_000,
  }),
  /** What the project added from the Hub, for model fields to offer; none in a published
   * dashboard. */
  hubAdded: () => ({
    queryKey: ["hub", "added"],
    queryFn: () =>
      isSnapshot()
        ? Promise.resolve<HubAdded>({ models: [], embeddings: [], datasets: [] })
        : get<HubAdded>("/hub/added"),
    retry: false,
  }),
  playground: () => ({
    queryKey: ["playground"],
    queryFn: () => get<PlaygroundInfo>("/playground"),
  }),
  compare: (a: string, b: string) => ({
    queryKey: ["compare", a, b],
    queryFn: () =>
      get<Comparison>(`/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  }),
  vectors: () => ({ queryKey: ["vectors"], queryFn: () => get<Direction[]>("/vectors") }),
  /** How alike one model's vectors are, as a figure; a published dashboard has none. */
  similarity: (model: string) => ({
    queryKey: ["similarity", model],
    queryFn: () => get<HeatmapView>(`/vectors/similarity?model=${encodeURIComponent(model)}`),
    enabled: !isSnapshot(),
  }),
  /** The training sets louped knows; a published dashboard has none. */
  trainingSets: () => ({
    queryKey: ["training-sets"],
    queryFn: () => (isSnapshot() ? Promise.resolve([]) : get<TrainingSet[]>("/training-sets")),
  }),
  trainingSet: (path: string) => ({
    queryKey: ["training-sets", path],
    queryFn: () => get<SetPairs>(`/training-sets/pairs?path=${encodeURIComponent(path)}`),
  }),
  graphs: () => ({ queryKey: ["graphs"], queryFn: () => get<Graph[]>("/graphs") }),
  graph: (slug: string) => ({
    queryKey: ["graphs", slug],
    queryFn: () => get<CircuitGraph>(`/graphs/${encodeURIComponent(slug)}`),
  }),
  launchables: () => ({
    queryKey: ["launchables"],
    queryFn: () => get<Launchable[]>("/launch"),
    retry: false,
  }),
  options: (id: string) => ({
    queryKey: ["options", id],
    queryFn: () => get<LaunchOption[]>(`/launch/options?id=${encodeURIComponent(id)}`),
    staleTime: Infinity,
  }),
  /** The clusters louped.toml names, to submit to. */
  clusters: () => ({
    queryKey: ["clusters"],
    queryFn: () => get<Cluster[]>("/launch/clusters"),
    staleTime: 30_000,
  }),
  jobs: () => ({
    queryKey: ["jobs"],
    queryFn: () => get<Job[]>("/launch/jobs"),
    refetchInterval: (query: Query<Job[]>) =>
      every(query.state.data?.some((j) => isLive(j.status))),
  }),
  job: (id: string) => ({
    queryKey: ["job", id],
    queryFn: () => get<JobDetail>(`/launch/jobs/${encodeURIComponent(id)}`),
    refetchInterval: (query: Query<JobDetail>) =>
      every(query.state.data && isLive(query.state.data.status)),
  }),
  /** What a page's regions show (louped.server.ui). poll follows layout.json as an agent edits
   * it, on a server that launches. */
  layout: (experiment: string | null | undefined, poll: boolean) => ({
    queryKey: ["layout", experiment ?? null],
    queryFn: () =>
      get<UiPage>(`/ui/layout${experiment ? `?experiment=${encodeURIComponent(experiment)}` : ""}`),
    refetchInterval: poll ? LAYOUT_MS : (false as const),
  }),
  theme: (poll: boolean) => ({
    queryKey: ["theme"],
    queryFn: () => get<Theme>("/ui/theme"),
    refetchInterval: poll ? LAYOUT_MS : (false as const),
  }),
  experiments: () => ({
    queryKey: ["experiments"],
    queryFn: () => get<Experiment[]>("/experiments"),
  }),
  cohorts: (experiment: string) => ({
    queryKey: ["cohorts", experiment],
    queryFn: () =>
      isSnapshot()
        ? Promise.resolve([] as SavedCohort[])
        : get<SavedCohort[]>(`/experiments/${encodeURIComponent(experiment)}/cohorts`),
  }),
  /** A board's table read from louped: a run's or experiment's file, metrics:<id> or runs:.
   * live is seconds between reads. */
  boardTable: (ref: string, live?: number | null) => ({
    queryKey: ["board-table", ref],
    queryFn: () => get<BoardTable>(`/board/table?ref=${encodeURIComponent(ref)}`),
    refetchInterval: () => (live && !isSnapshot() ? live * 1000 : false),
  }),
  /** The boards shown as their own pages; a published dashboard has none. Polled, so a page an
   * agent adds shows in the sidebar. */
  boards: () => ({
    queryKey: ["boards"],
    queryFn: () => (isSnapshot() ? Promise.resolve([]) : get<BoardPage[]>("/boards")),
    retry: false,
    refetchInterval: () => (isSnapshot() ? false : 3000),
  }),
  board: (name: string) => ({
    queryKey: ["boards", name],
    queryFn: () => get<BoardView>(`/boards/${encodeURIComponent(name)}`),
    refetchInterval: () => (isSnapshot() ? false : 3000),
  }),
  /** An experiment's own figures; a published dashboard has none. */
  experimentViews: (experiment: string) => ({
    queryKey: ["experiment-views", experiment],
    queryFn: () =>
      isSnapshot()
        ? Promise.resolve([] as RunView[])
        : get<RunView[]>(`/experiments/${encodeURIComponent(experiment)}/views`),
  }),
  /** louped's judge and the project's judges/<name>.py; a published dashboard judges nothing. */
  judges: () => ({
    queryKey: ["judges"],
    queryFn: () => (isSnapshot() ? Promise.resolve([] as Judge[]) : get<Judge[]>("/judges")),
  }),
  /** Two eval runs' shared samples as blind pairs, with the person's picks. */
  ab: (a: string, b: string) => ({
    queryKey: ["ab", a, b],
    queryFn: () => get<AbSession>(`/ab?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  }),
  abResult: (a: string, b: string) => ({
    queryKey: ["ab-result", a, b],
    queryFn: () =>
      get<AbResult>(`/ab/result?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  }),
  /** Every Inspect task Launch's eval runs: the project's, then inspect_evals'. */
  evalTasks: () => ({
    queryKey: ["eval-tasks"],
    queryFn: () => get<EvalTask[]>("/evals"),
  }),
  experiment: (name: string) => ({
    queryKey: ["experiment", name],
    queryFn: () => get<ExperimentDetail>(`/experiments/${encodeURIComponent(name)}`),
  }),
};
