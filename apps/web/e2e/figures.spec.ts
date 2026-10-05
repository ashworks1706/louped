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

test("a figure's point says which item it is and where it comes from, and opens it", async ({
  page,
}, info) => {
  await mock(page);
  const points = {
    kind: "plotly",
    title: "Claims by embedding",
    data: [{ type: "scatter", mode: "markers", x: [0, 1], y: [0, 1], ids: ["28", "29"] }],
    layout: {},
    items: { folder: "raw" },
  };
  const withViews = {
    ...run,
    artifacts: [...run.artifacts, { path: "views/claims.json", size: 1 }],
  };
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: withViews }));
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/claims.json", view: points }] }),
  );
  const asked: string[] = [];
  await page.route("**/api/trace?*", (r) => {
    const ref = new URL(r.request().url()).searchParams.get("ref")!;
    asked.push(ref);
    const item = ref.split("#")[1];
    return r.fulfill({
      json: {
        ref,
        steps: [
          { ref: "run:m-1/views/claims.json", what: "figure", title: "Claims by embedding" },
          {
            ref: "run:m-1/derived/claims.py",
            what: "script",
            title: "derived/claims.py",
            commit: "a1b2c3d4e5f6",
            dirty: false,
          },
          {
            ref: `run:m-1/raw/baseline.jsonl#${item}`,
            what: "item",
            title: `item ${item} in raw`,
            rows: { "raw/baseline.jsonl": {}, "raw/pressure.jsonl": {} },
          },
          { ref: "run:m-1", what: "run", title: "r", commit: "a1b2c3d4e5f6", dirty: false },
        ],
      },
    });
  });
  await page.goto("/run/?id=m-1&tab=figures");
  const figure = page.locator('[data-part="figures/figure/views%2Fclaims.json"]');
  const readout = figure.getByTestId("mark-trace");
  await expect(readout).toContainText("Hover a point");
  const point = figure.locator(".scatterlayer .point").first();
  await expect(point).toBeVisible();
  const box = (await point.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(readout).toHaveText("item 28 · 2 files · derived/claims.py at a1b2c3d");
  await page.screenshot({ path: info.outputPath("mark-trace.png"), fullPage: true });
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page).toHaveURL(/tab=items&set=raw&item=28/);
  expect(asked).toContain("run:m-1/views/claims.json#28");
});

test("a vega chart's mark names its item, and a click that cannot open it says why", async ({
  page,
}) => {
  await mock(page);
  const chart = {
    kind: "vega",
    title: "Confidence by item",
    spec: {
      mark: { type: "point", size: 400, filled: true },
      data: { values: [{ qid: 30, x: 1, y: 1 }] },
      encoding: {
        x: { field: "x", type: "quantitative" },
        y: { field: "y", type: "quantitative" },
      },
    },
    items: { field: "qid" },
  };
  const withViews = {
    ...run,
    artifacts: [...run.artifacts, { path: "views/conf.json", size: 1 }],
  };
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: withViews }));
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/conf.json", view: chart }] }),
  );
  await page.route("**/api/trace?*", (r) =>
    r.fulfill({ status: 400, json: { detail: "no item '30' in raw of run m-1" } }),
  );
  await page.goto("/run/?id=m-1&tab=figures");
  const figure = page.locator("figure", { hasText: "Confidence by item" });
  const point = figure.locator(".mark-symbol path").first();
  await expect(point).toBeVisible();
  await point.hover();
  await expect(figure.getByTestId("mark-trace")).toContainText("item 30");
  await point.click();
  await expect(figure.getByTestId("mark-trace")).toContainText("no item '30' in raw");
  await expect(page).toHaveURL(/tab=figures/);
});
