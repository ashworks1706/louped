import type { Page } from "@playwright/test";

// The Datasets and Benchmarks pages over a mocked API: two Hub datasets (one filed under
// Behavior), a file under data/, a training set; eval tasks with runs; louped bench runs.

export const datasets = [
  { id: "openai/gsm8k", source: "hub", domains: ["behavior"], path: null, format: null,
    size: null, rows: null, error: null }, // prettier-ignore
  { id: "cais/mmlu", source: "hub", domains: [], path: null, format: null, size: null,
    rows: null, error: null }, // prettier-ignore
  { id: "data/pairs.jsonl", source: "local", domains: [], path: "/home/me/proj/data/pairs.jsonl",
    format: "jsonl", size: 2048, rows: null, error: null }, // prettier-ignore
  { id: "pushback.jsonl", source: "training", domains: [],
    path: "/home/me/.louped/data/pushback/pushback.jsonl", format: "dpo", size: null, rows: 2,
    error: null }, // prettier-ignore
];

const gsm8kHub = {
  kind: "datasets",
  id: "openai/gsm8k",
  url: "https://huggingface.co/datasets/openai/gsm8k",
  downloads: 420_000,
  likes: 800,
  task: null,
  library: null,
  gated: false,
  private: false,
  updated: "2026-08-01T00:00:00Z",
  params: null,
  title: null,
  authors: [],
  upvotes: null,
  card: "# GSM8K\n\nGrade school maths word problems.",
  license: "mit",
  tags: ["task_categories:text-generation"],
  size: 5_000_000,
  files: 6,
  summary: null,
  links: {},
};

export const gsm8k = {
  id: "openai/gsm8k",
  source: "hub",
  hub: gsm8kHub,
  hub_error: null,
  splits: [
    { config: "main", split: "train", rows: 7473 },
    { config: "main", split: "test", rows: 1319 },
    { config: "socratic", split: "test", rows: null },
  ],
  config: "main",
  split: "train",
  features: [
    { name: "question", type: "string" },
    { name: "answer", type: "string" },
  ],
  rows: [
    { question: "Natalia sold clips to 48 of her friends. How many?", answer: "#### 72" },
    { question: "Weng earns $12 an hour. How much for 50 minutes?", answer: "#### 10" },
  ],
  total: 7473,
  error: null,
};

const pairs = {
  id: "data/pairs.jsonl",
  source: "local",
  hub: null,
  hub_error: null,
  splits: [],
  config: null,
  split: "jsonl",
  features: [
    { name: "prompt", type: "string" },
    { name: "answer", type: "int64" },
  ],
  rows: [{ prompt: "2+2?", answer: 4 }],
  total: 1,
  error: null,
};

const task = (t: string, title: string, group: string, source: string, about: string | null) => ({
  task: t,
  title,
  group,
  about,
  samples: null,
  source,
});
const entry = (run: string, model: string, score: number, created: string) => ({
  run,
  model,
  score,
  metric: "match/accuracy",
  samples: 50,
  created,
});
export const spec = {
  dataset: "openai/gsm8k",
  config: "main",
  split: "test",
  input: "question",
  target: "answer",
  choices: null,
  scorer: "match",
};
export const benchmarks = [
  {
    task: task("louped/gsm8k", "gsm8k", "Hub benchmarks", "benchmark",
               "openai/gsm8k (main), test: question to answer, scored by match."), // prettier-ignore
    runs: 2,
    best: entry("e-1", "louped/Qwen/Qwen2.5-1.5B-Instruct", 0.62, "2026-10-10T00:00:00Z"),
    spec,
  },
  {
    task: task("inspect_evals/arc_easy", "ARC", "Reasoning", "inspect_evals", "Science questions."),
    runs: 1,
    best: entry("e-2", "louped/tiny", 0.41, "2026-10-09T00:00:00Z"),
    spec: null,
  },
  {
    task: task("experiments/hello/task.py@hi", "hi", "hello", "project", "Says hi."),
    runs: 0,
    best: null,
    spec: null,
  },
  {
    task: task("inspect_evals/mmlu_0_shot", "MMLU", "Knowledge", "inspect_evals", "Knowledge."),
    runs: 0,
    best: null,
    spec: null,
  },
];
export const board = {
  task: benchmarks[0].task,
  spec,
  entries: [
    entry("e-1", "louped/Qwen/Qwen2.5-1.5B-Instruct", 0.62, "2026-10-10T00:00:00Z"),
    entry("e-3", "louped/Qwen/Qwen2.5-0.5B-Instruct", 0.31, "2026-10-08T00:00:00Z"),
  ],
};
const speed = (run: string, model: string, setting: string, tps: number, best: boolean) => ({
  run,
  model,
  setting,
  device: "cuda:0",
  weights_mib: setting === "int8" ? 520 : 940,
  throughput: tps,
  batch: 16,
  prefill_ms: 42.5,
  context: 8192,
  peak_mib: 1800,
  created: "2026-10-10T00:00:00Z",
  best,
});
export const speedRows = [
  speed("m-9", "Qwen/Qwen2.5-0.5B-Instruct", "as saved", 812.4, false),
  speed("m-9", "Qwen/Qwen2.5-0.5B-Instruct", "int8", 990.1, true),
  speed("m-8", "Qwen/Qwen2.5-1.5B-Instruct", "as saved", 402.0, true),
];

export async function mockDatasets(page: Page) {
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/datasets", datasets);
  await json("**/api/datasets/hub?*", gsm8k);
  await json("**/api/datasets/local?*", pairs);
  await json("**/api/benchmarks", benchmarks);
  await json("**/api/benchmarks/board?*", board);
  await json("**/api/benchmarks/speed", speedRows);
}
