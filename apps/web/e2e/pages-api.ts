import type { Page } from "@playwright/test";

import { mock, run, summary } from "./items-run";
import { mockReports } from "./reports-api";
import { mockSources } from "./sources-api";

// The rest of the app over a mocked API, on top of items-run's run m-1: an eval run with
// samples (e-1), a training run with curves (t-1), a vector, a graph, a feature, a script to
// launch and a job that ran it.
const evalRun = {
  ...run,
  id: "e-1",
  kind: "eval",
  name: "task",
  metrics: { "match/accuracy": 0.5 },
  samples: 2,
  total: 2,
  artifacts: [],
  scorers: ["match"],
  log: "2026_task.eval",
};
const trainRun = {
  ...run,
  id: "t-1",
  kind: "training",
  name: "sft",
  metrics: { loss: 0.4 },
  history: {
    loss: [
      { step: 0, value: 1.2, timestamp: 0 },
      { step: 1, value: 0.7, timestamp: 1 },
      { step: 2, value: 0.4, timestamp: 2 },
    ],
  },
  artifacts: [],
};
const trainAgain = {
  ...trainRun,
  id: "t-2",
  name: "sft · lr 1e-4",
  history: { loss: trainRun.history.loss.map((p) => ({ ...p, value: p.value * 0.8 })) },
};
const summaries = [summary, evalRun, trainRun, trainAgain].map((r) => ({
  ...r,
  artifacts: undefined,
}));
const vector = {
  name: "caving",
  model: "tiny",
  layer: 1,
  method: "diff-in-means",
  norm: 1,
  dim: 8,
  run: "m-1",
  notes: null,
  created: "2026-10-03T00:00:00Z",
};
const job = {
  id: "j1",
  title: "hello/run.py",
  argv: ["python", "experiments/hello/run.py"],
  status: "succeeded",
  created: "2026-10-05T00:00:00Z",
  started: "2026-10-05T00:00:01Z",
  ended: "2026-10-05T00:00:09Z",
  exit_code: 0,
};
const feature = {
  feature: 12,
  hook: "blocks.1.hook_resid_post",
  layer: 1,
  density: 0.01,
  max: 3,
  histogram: { edges: [0, 1, 2, 3], counts: [5, 2, 1] },
  promoted: [["sure", 0.9]],
  suppressed: [["no", -0.8]],
  examples: {
    kind: "tokens",
    title: "Top examples",
    rows: [{ tokens: ["hi", "!"], values: { act: [0, 3] } }],
  },
  neuronpedia: null,
};

export async function mockPages(page: Page, parts: Record<string, object> = {}) {
  await mock(page, parts);
  await mockSources(page);
  await mockReports(page);
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/runs", summaries);
  await json("**/api/runs/e-1", evalRun);
  await json("**/api/runs/e-1/views", []);
  await json("**/api/runs/e-1/samples", [
    { id: "1", epoch: 1, input: "2+2?", target: "4", scores: { match: 1 }, error: null },
    { id: "2", epoch: 1, input: "3+3?", target: "6", scores: { match: 0 }, error: null },
  ]);
  await json("**/api/runs/e-1/samples/1?*", {
    id: "1",
    epoch: 1,
    target: "4",
    messages: [
      { role: "user", text: "2+2?", tool_calls: [] },
      { role: "assistant", text: "4", tool_calls: [] },
    ],
    scores: [{ name: "match", value: 1, raw: "C", answer: "4", explanation: null }],
    metadata: {},
    error: null,
  });
  await json("**/api/runs/e-1/labels", {});
  await json("**/api/runs/e-1/agreement", { labelled: 0, total: 2, agreement: null, kappa: null });
  await json("**/api/runs/t-1", trainRun);
  await json("**/api/runs/t-1/views", []);
  await json("**/api/runs/t-2", trainAgain);
  await json("**/api/runs/m-1/features", [12, 13]);
  await json("**/api/runs/m-1/features/12", feature);
  await json("**/api/playground", {
    model: "tiny",
    layers: 2,
    heads: 4,
    bank: [],
    diffusion: false,
    switchable: true,
  });
  await json("**/api/vectors", [vector, { ...vector, name: "refusal", layer: 0 }]);
  await json("**/api/vectors/similarity?*", {
    kind: "heatmap",
    title: "How alike they are",
    x: ["caving", "refusal"],
    y: ["caving", "refusal"],
    z: [
      [1, 0.12],
      [0.12, 1],
    ],
    x_label: "vector",
    y_label: "vector",
    labels: [
      ["1.00", "0.12"],
      ["0.12", "1.00"],
    ],
    about: "The cosine between each pair of directions.",
  });
  await json("**/api/graphs", [
    { slug: "capital", prompt: "The capital of France is", scan: null },
  ]);
  await page.route("**/circuit/**", (r) =>
    r.fulfill({ body: "<title>Attribution Graphs</title>" }),
  );
  await json("**/api/compare?*", {
    a: "m-1",
    b: "e-1",
    only_a: 0,
    only_b: 0,
    scores: [
      { name: "match", n: 2, mean_a: 1, mean_b: 0.5, diff: -0.5, low: -1, high: 0, up: 0, down: 1 },
    ],
  });
  await json("**/api/launch", [
    {
      id: "script:hello/run.py",
      group: "Experiments",
      title: "hello/run.py",
      description: "Say hello.",
      config: null,
      recipe: null,
    },
  ]);
  await json("**/api/launch/options?*", [
    { flag: "--name", kind: "text", default: "world", help: "Who to greet.", choices: [] },
    { flag: "--loud", kind: "bool", default: "False", help: "", choices: [] },
  ]);
  await json("**/api/launch/jobs", [job]);
  await json("**/api/launch/jobs/j1", { ...job, log: '{"run": "m-1"}\nhello\n' });
}
