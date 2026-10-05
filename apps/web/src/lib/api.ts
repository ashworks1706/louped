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
export type Experiment = Schemas["Experiment"];
export type ExperimentDetail = Schemas["ExperimentDetail"];
type RunView = Schemas["RunView"];
export type HeatmapView = Schemas["HeatmapView"];
export type LineView = Schemas["LineView"];
export type TableView = Schemas["TableView"];
export type ScatterView = Schemas["ScatterView"];
export type TokensView = Schemas["TokensView"];
export type VegaView = Schemas["VegaView"];
export type Pushed = Schemas["Pushed"];
export type View = RunView["view"];
export type Direction = Schemas["Direction"];
type Graph = Schemas["Graph"];
type Comparison = Schemas["Comparison"];
export type PlaygroundInfo = Schemas["PlaygroundInfo"];
type GenerateRequest = Schemas["GenerateRequest"];
type InspectRequest = Schemas["InspectRequest"];
type InspectResponse = Schemas["InspectResponse"];
export type FeatureDashboard = Schemas["FeatureDashboard"];
export type Launchable = Schemas["Launchable"];
export type LaunchOption = Schemas["Option"];
export type LaunchRequest = Schemas["LaunchRequest"];
export type Job = Schemas["Job"];
export type Target = Schemas["Target"];
/** The server fills in any target field left out with its default. */
export type ExportRequest = LaunchRequest & {
  target: Partial<Target> & Pick<Target, "provider">;
};
export type Imported = Schemas["Imported"];
export type Agreement = Schemas["Agreement"];
export type Label = "a" | "b" | "tie";
type JobDetail = Schemas["JobDetail"];

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

/** Pushes this louped's new runs to the project's remote. */
export const pushRuns = () => post<Pushed>("/launch/push", {});
/** Adds the runs in the remote this louped has not pulled. */
export const pullRuns = () => post<Imported[]>("/launch/pull", {});

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
export const loadModel = (req: Schemas["LoadRequest"]) =>
  post<PlaygroundInfo>("/playground/load", req);
export const cancelJob = (id: string) =>
  post<Job>(`/launch/jobs/${encodeURIComponent(id)}/cancel`, {});

/** A run still writing (Inspect says started, MLflow running), or a job not yet ended. */
export const isLive = (status: string) =>
  status === "started" || status === "running" || status === "queued";

/** How often a page refetches a run that is still writing. */
const LIVE_MS = 3000;
const every = (live: boolean | undefined): number | false => (live ? LIVE_MS : false);

/** Query keys and fetchers, one per endpoint, so pages never build URLs by hand. Queries over a
 * live run poll until it ends. */
export const q = {
  health: () => ({ queryKey: ["health"], queryFn: () => get<Health>("/health"), retry: false }),
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
  graphs: () => ({ queryKey: ["graphs"], queryFn: () => get<Graph[]>("/graphs") }),
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
  experiments: () => ({
    queryKey: ["experiments"],
    queryFn: () => get<Experiment[]>("/experiments"),
  }),
  experiment: (name: string) => ({
    queryKey: ["experiment", name],
    queryFn: () => get<ExperimentDetail>(`/experiments/${encodeURIComponent(name)}`),
  }),
};
