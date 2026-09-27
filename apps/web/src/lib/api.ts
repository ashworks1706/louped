import type { components } from "@/lib/api-types";

/** The API origin: set in development, the same origin when served by `loupe serve`. */
export const API = process.env.NEXT_PUBLIC_LOUPE_API ?? "";

type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type RunSummary = Schemas["RunSummary"];
export type RunDetail = Schemas["RunDetail"];
export type SampleSummary = Schemas["SampleSummary"];
export type SampleDetail = Schemas["SampleDetail"];
export type Experiment = Schemas["Experiment"];
export type RunView = Schemas["RunView"];
export type HeatmapView = Schemas["HeatmapView"];
export type LineView = Schemas["LineView"];
export type TableView = Schemas["TableView"];
export type Direction = Schemas["Direction"];
export type PlaygroundInfo = Schemas["PlaygroundInfo"];
export type GenerateRequest = Schemas["GenerateRequest"];
export type GenerateResponse = Schemas["GenerateResponse"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API}/api${path}`, { signal });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
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
  return res.json() as Promise<T>;
}

export const generate = (req: GenerateRequest) =>
  post<GenerateResponse>("/playground/generate", req);

export const health = (signal?: AbortSignal) => get<Health>("/health", signal);

/** Query keys and fetchers, one per endpoint, so pages never build URLs by hand. */
export const q = {
  runs: () => ({ queryKey: ["runs"], queryFn: () => get<RunSummary[]>("/runs") }),
  run: (id: string) => ({
    queryKey: ["run", id],
    queryFn: () => get<RunDetail>(`/runs/${encodeURIComponent(id)}`),
  }),
  samples: (id: string) => ({
    queryKey: ["samples", id],
    queryFn: () => get<SampleSummary[]>(`/runs/${encodeURIComponent(id)}/samples`),
  }),
  sample: (id: string, sample: string, epoch = 1) => ({
    queryKey: ["sample", id, sample, epoch],
    queryFn: () =>
      get<SampleDetail>(
        `/runs/${encodeURIComponent(id)}/samples/${encodeURIComponent(sample)}?epoch=${epoch}`,
      ),
  }),
  views: (id: string) => ({
    queryKey: ["views", id],
    queryFn: () => get<RunView[]>(`/runs/${encodeURIComponent(id)}/views`),
  }),
  playground: () => ({
    queryKey: ["playground"],
    queryFn: () => get<PlaygroundInfo>("/playground"),
  }),
  vectors: () => ({ queryKey: ["vectors"], queryFn: () => get<Direction[]>("/vectors") }),
  experiments: () => ({
    queryKey: ["experiments"],
    queryFn: () => get<Experiment[]>("/experiments"),
  }),
};
