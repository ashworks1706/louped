import { expect, test } from "./fixtures";
import { files, mock, run } from "./items-run";

// What an agent adds from a run's files: a Plotly figure (3D, animated) on a run or on the
// experiment's page, and derived columns beside the conditions in Items.
const cloud = {
  kind: "plotly",
  title: "Claims in 3D",
  about: "Each point is a claim's embedding, coloured by whether pressure flipped it.",
  data: [{ type: "scatter3d", mode: "markers", x: [0, 1], y: [1, 0], z: [0.5, 0.2] }],
  frames: [
    { name: "0", data: [{ x: [0, 1] }] },
    { name: "1", data: [{ x: [1, 0] }] },
  ],
};

test("a Plotly figure an agent added shows on the run, with its frames", async ({ page }, info) => {
  await mock(page);
  const withViews = {
    ...run,
    artifacts: [...run.artifacts, { path: "views/claims-3d.json", size: 1 }],
  };
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: withViews }));
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/claims-3d.json", view: cloud }] }),
  );
  await page.goto("/run/?id=m-1&tab=figures");
  const figure = page.locator('[data-part="figures/figure/views%2Fclaims-3d.json"]');
  await expect(figure).toContainText("Claims in 3D");
  await expect(figure.getByTestId("plotly").locator(".main-svg").first()).toBeVisible();
  await expect(figure.getByText("Play")).toBeVisible();
  await page.screenshot({ path: info.outputPath("run-plotly.png"), fullPage: true });
});

test("an experiment's page shows the figures an agent put there", async ({ page }, info) => {
  await mock(page);
  await page.route("**/api/experiments/hello/views", (r) =>
    r.fulfill({ json: [{ path: "views/claims-3d.json", view: cloud }] }),
  );
  await page.goto("/behavior/experiment/?name=hello");
  const figure = page.locator('[data-part="experiment/view/views%2Fclaims-3d.json"]');
  await expect(figure).toContainText("Claims in 3D");
  await expect(figure.getByTestId("plotly").locator(".main-svg").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("experiment-views.png"), fullPage: true });
});

test("derived columns sit beside the conditions in Items", async ({ page }, info) => {
  const derived = "derived/hedged.jsonl";
  files[derived] = '{"qid": 28, "hedged": true}\n{"qid": 29, "hedged": false}\n';
  run.artifacts.push({ path: derived, size: files[derived].length });
  try {
    await mock(page);
    await page.goto("/run/?id=m-1&tab=items");
    await expect(page.getByRole("columnheader", { name: "hedged.hedged" })).toBeVisible();
    await expect(page.locator('[data-part="items/cell/28/hedged.hedged"]')).toHaveText("true");
    await page.screenshot({ path: info.outputPath("derived.png"), fullPage: true });
  } finally {
    delete files[derived];
    run.artifacts.pop();
  }
});

test("a derived file without the items' key says so instead of showing nothing", async ({
  page,
}) => {
  const derived = "derived/loose.jsonl";
  files[derived] = '{"label": "x"}\n';
  run.artifacts.push({ path: derived, size: files[derived].length });
  try {
    await mock(page);
    await page.goto("/run/?id=m-1&tab=items");
    await expect(page.getByText("derived/loose.jsonl has no qid")).toBeVisible();
  } finally {
    delete files[derived];
    run.artifacts.pop();
  }
});
