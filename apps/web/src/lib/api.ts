import type { Query } from "@tanstack/react-query";

import type { components } from "@/lib/api-types";

/** The API origin: set in development, the same origin when served by `loupe serve`. */
export const API = process.env.NEXT_PUBLIC_LOUPE_API ?? "";

type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type RunSummary = Schemas["RunSummary"];
export type RunDetail = Schemas["RunDetail"];
export type SampleSummary = Schemas["SampleSummary"];
export type SampleDetail = Schemas["SampleDetail"];
type Experiment = Schemas["Experiment"];
export type RunView = Schemas["RunView"];
export type HeatmapView = Schemas["HeatmapView"];
export type LineView = Schemas["LineView"];
export type TableView = Schemas["TableView"];
export type TokensView = Schemas["TokensView"];
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
type JobDetail = Schemas["JobDetail"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API}/api${path}`, { signal });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

async function send(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`${API}/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b: { detail?: unknown }) => b.detail)
      .catch(() => null);
    throw new ApiError(res.status, typeof detail === "string" ? detail : `${res.status} ${path}`);
  }
  return res;
}

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

export const health = (signal?: AbortSignal) => get<Health>("/health", signal);

export const launch = (req: LaunchRequest) => post<Job>("/launch", req);
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
};
