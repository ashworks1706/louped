import type { Page } from "@playwright/test";

// A board an agent kept as a page: items by model, linked to a table, a stat, a detail, a
// Plotly curve that plays over steps and a diagram of the pipeline.
export const scores = {
  kind: "board",
  title: "Scores by model",
  about: "Pick a model; every panel follows.",
  section: "behavior",
  data: {
    items: { ref: "run:m-1/raw/items.jsonl" },
    loss: { ref: "metrics:m-1", live: 5 },
    nodes: { rows: [{ id: "data", stage: "in" }, { id: "train", stage: "run" }, { id: "eval", stage: "out" }] }, // prettier-ignore
    links: { rows: [{ from: "data", to: "train" }, { from: "train", to: "eval" }] }, // prettier-ignore
  },
  controls: [
    { id: "model", kind: "select", data: "items", field: "model", label: "Model", about: "Which model's items." }, // prettier-ignore
    { id: "min", kind: "range", min: 0, max: 1, step: 0.1, default: 0, label: "Score at least" }, // prettier-ignore
  ],
  panels: [
    { id: "rows", kind: "table", title: "Items", data: "items", span: 2, select: { param: "qid", field: "qid" },
      where: [{ field: "model", param: "model" }, { field: "score", op: ">=", param: "min" }] }, // prettier-ignore
    { id: "mean", kind: "stat", title: "Mean score", about: "Mean of the items shown.", data: "items", op: "mean", field: "score", format: "percent", span: 1,
      where: [{ field: "model", param: "model" }, { field: "score", op: ">=", param: "min" }] }, // prettier-ignore
    { id: "one", kind: "detail", title: "Picked item", data: "items", span: 1, where: [{ field: "qid", param: "qid" }] }, // prettier-ignore
    { id: "curve", kind: "plotly", title: "Loss", data: "loss", trace: "line", x: "step", y: "value", color: "key", span: 2 }, // prettier-ignore
    { id: "flow", kind: "diagram", title: "Pipeline", data: "nodes", edges: "links", node: "id", source: "from", target: "to", color: "stage", span: 2 }, // prettier-ignore
  ],
};

const items = [
  { qid: 1, model: "base", score: 0.2, claim: "The sky is green." },
  { qid: 2, model: "dpo", score: 0.9, claim: "Water boils at 100 C." },
  { qid: 3, model: "dpo", score: 0.6, claim: "Paris is in Spain." },
];
const loss = [0, 1, 2].map((step) => ({
  key: "loss",
  step,
  value: 2 / (step + 1),
  timestamp: null,
}));

export async function mockBoards(page: Page) {
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/boards", [{ name: "scores", title: scores.title, about: scores.about, section: "behavior" }]); // prettier-ignore
  await json("**/api/boards/scores", scores);
  await page.route("**/api/board/table?*", (r) => {
    const ref = new URL(r.request().url()).searchParams.get("ref");
    const rows = ref === "metrics:m-1" ? loss : items;
    return r.fulfill({ json: { rows, columns: Object.keys(rows[0]), truncated: false } });
  });
}
