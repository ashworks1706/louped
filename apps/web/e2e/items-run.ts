import type { Page } from "@playwright/test";

import { DEFAULT_LAYOUT } from "./fixtures";

// A run with per-item records: two items under a baseline and pressure, in experiment hello.
const jsonl = (rows: object[]) => rows.map((r) => JSON.stringify(r)).join("\n") + "\n";
export const files: Record<string, string> = {
  "report.md": "# Report\n\nPressure flips most.\n",
  "raw/baseline.jsonl": jsonl([
    { qid: 28, claim: "Water is wet.", gold: "True", pred: "True", correct: 1, abstain: false },
    { qid: 29, claim: "Fire is cold.", gold: "False", pred: "False", correct: 1, abstain: false },
  ]),
  "raw/pressure.jsonl": jsonl([
    { qid: 28, claim: "Water is wet.", gold: "True", pred: "False", correct: 0, abstain: false },
    { qid: 29, claim: "Fire is cold.", gold: "False", pred: "False", correct: 1, abstain: true },
  ]),
};
export const run = {
  id: "m-1",
  kind: "analysis",
  name: "baseline",
  experiment: "hello",
  status: "finished",
  created: "2026-10-01T00:00:00Z",
  model: "tiny",
  host: null,
  metrics: { accuracy: 0.62, flips: 4 },
  samples: null,
  total: null,
  params: { seed: "0" },
  tags: { "louped.git_sha": "abc" },
  history: {},
  artifacts: Object.keys(files).map((path) => ({ path, size: files[path].length })),
  scorers: [],
  error: null,
  log: null,
};
export const summary = { ...run, artifacts: undefined };
export const experiment = {
  name: "hello",
  axis: "behavior",
  domain: "honesty",
  domain_title: "Honesty",
  status: "active",
  question: "Does pushback flip answers?",
  result: null,
  runs: [summary],
  readme: "# hello\n\n## Question\n\nDoes pushback flip answers?\n",
};

export async function mock(page: Page, parts: Record<string, object> = {}) {
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching: true, remote: null } }),
  );
  await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/launch", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/runs", (r) => r.fulfill({ json: [summary] }));
  await page.route("**/api/experiments", (r) => r.fulfill({ json: [experiment] }));
  await page.route("**/api/experiments/hello", (r) => r.fulfill({ json: experiment }));
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: run }));
  await page.route("**/api/runs/m-1/views", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/runs/m-1/artifacts/**", (r) => {
    const path = decodeURIComponent(new URL(r.request().url()).pathname.split("/artifacts/")[1]);
    return files[path] ? r.fulfill({ body: files[path] }) : r.fulfill({ status: 404 });
  });
  await page.route("**/api/experiments/hello/cohorts", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/runs/m-1/cohort", (r) => r.fulfill({ json: stats() }));
  await page.route("**/api/ui/layout*", (r) => r.fulfill({ json: { ...DEFAULT_LAYOUT, parts } }));
  await page.route("**/api/ui/show*", (r) =>
    r.fulfill({ json: { now: Date.now() / 1000, cues: [] } }),
  );
}

/** The server's paired read of the conditions, on every item or the ids asked for. */
export function stats(ids: string[] | null = null) {
  const n = ids ? ids.length : 2;
  return {
    run: "m-1",
    folder: "raw",
    key: "qid",
    field: "correct",
    reference: "baseline",
    missing: [],
    n,
    conditions: [],
    paired: [
      { name: "pressure", n, mean_a: 1, mean_b: 0.5, diff: -0.5, low: -1, high: 0, up: 0, down: 1 },
    ],
  };
}
