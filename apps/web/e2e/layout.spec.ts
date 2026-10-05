import type { Page } from "@playwright/test";

import { DEFAULT_LAYOUT, expect, test } from "./fixtures";

// A run's page laid out by the person's agent: its layout.json as the server answers it.
const jsonl = (rows: object[]) => rows.map((r) => JSON.stringify(r)).join("\n") + "\n";
const claim = "The Shape of Water is a 2017 film by the director of Creed.";
const files: Record<string, string> = {
  "examples.md": "# Examples\n\nVerdict: **right**\n",
  "raw/baseline.jsonl": jsonl([
    { qid: 28, claim, gold: "True", pred: "True", correct: 1, condition: "baseline" },
    { qid: 29, claim: "Other.", gold: "False", pred: "False", correct: 1, condition: "baseline" },
  ]),
  "raw/pressure.jsonl": jsonl([
    { qid: 28, claim, gold: "True", pred: "False", correct: 0, condition: "pressure" },
    { qid: 29, claim: "Other.", gold: "False", pred: "False", correct: 1, condition: "pressure" },
  ]),
  "raw/fields.json": JSON.stringify({ pred: "The verdict the scorer read from the reply." }),
};
const run = {
  id: "m-1",
  kind: "analysis",
  name: "baseline",
  experiment: "hello",
  status: "finished",
  created: null,
  model: null,
  metrics: { accuracy: 0.62, flips: 4 },
  samples: null,
  params: {},
  tags: {},
  history: {},
  artifacts: Object.keys(files).map((path) => ({ path, size: files[path].length })),
  scorers: [],
  error: null,
  log: null,
};

const layout = {
  ...DEFAULT_LAYOUT,
  regions: {
    ...DEFAULT_LAYOUT.regions,
    "run.tabs": [
      { block: "overview", title: "Summary", width: "full" },
      { block: "items", width: "full" },
      { block: "file", path: "examples.md", title: "Examples", width: "full" },
      { block: "samples", width: "full" }, // not an eval: no tab
    ],
    "run.overview": [
      { block: "text", text: "Read **flips** first.", width: "full" },
      { block: "metric", key: "accuracy", width: "half" },
      { block: "metric", key: "flips", width: "half" },
      { block: "file", path: "examples.md", width: "full" },
    ],
  },
  sources: { ...DEFAULT_LAYOUT.sources, "run.overview": "experiments/hello/layout.json" },
  errors: ["layout.json: run.tabs[0]: 'chart' is not a block of run.tabs"],
};

async function mock(page: Page, launching = true) {
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching, remote: null } }),
  );
  await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: run }));
  await page.route("**/api/runs/m-1/artifacts/**", (r) => {
    const path = decodeURIComponent(new URL(r.request().url()).pathname.split("/artifacts/")[1]);
    return r.fulfill({ body: files[path] });
  });
  await page.route("**/api/ui/layout*", (r) => r.fulfill({ json: layout }));
}

test("a run's page follows the layout its agent wrote, and says what it could not use", async ({
  page,
}, info) => {
  await mock(page);
  await page.goto("/run/?id=m-1");
  await expect(page.getByRole("tab")).toHaveText(["Summary", "Items", "Examples"]);
  const overview = page.locator('[data-ui="run.overview/metric/accuracy"]');
  await expect(overview).toContainText("0.62");
  await expect(page.locator('[data-ui="run.overview/text/0"] strong')).toHaveText("flips");
  await expect(page.locator('[data-ui="run.overview/file/examples.md"] strong')).toHaveText(
    "right",
  );
  await expect(page.getByRole("alert").filter({ hasText: "Not used" })).toContainText(
    "'chart' is not a block of run.tabs",
  );
  await page.screenshot({ path: info.outputPath("layout-run.png"), fullPage: true });
  await page.getByRole("tab", { name: "Examples" }).click();
  await expect(page.getByRole("tabpanel").getByText("Verdict:")).toBeVisible();
});

test("a shared page shows the layout and keeps its errors to itself", async ({ page }) => {
  await mock(page, false);
  await page.goto("/run/?id=m-1");
  await expect(page.getByRole("tab", { name: "Summary" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "Not used" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Point your agent at a block" })).toHaveCount(0);
});

test("pointing at a card hands it to the agent and copies its reference", async ({
  page,
  context,
}, info) => {
  test.skip(info.project.name === "mobile", "the top bar's crosshair is a pointer's tool");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await mock(page);
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/ui/selection", (r) => {
    sent = r.request().postDataJSON() as Record<string, unknown>;
    return r.fulfill({ json: sent });
  });
  await page.goto("/run/?id=m-1");
  await page.getByRole("button", { name: "Point your agent at a block" }).click();
  const card = page.locator('[data-ui="run.overview/metric/accuracy"]');
  await card.hover();
  await expect(card).toHaveAttribute("data-ui-hover", "");
  await page.screenshot({ path: info.outputPath("layout-select.png") });
  await card.click();
  await expect(page.getByText("Your agent can see run.overview/metric/accuracy")).toBeVisible();
  expect(sent).toMatchObject({
    id: "run.overview/metric/accuracy",
    run: "m-1",
    url: "/run/?id=m-1",
  });
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("louped block run.overview/metric/accuracy");
  expect(copied).toContain("run: m-1");
  // the mode ends with the click; the next click acts again
  await expect(page.locator("html")).not.toHaveAttribute("data-selecting");
});

test("louped.toml's theme sets the app's tokens", async ({ page }) => {
  await mock(page);
  await page.route("**/api/ui/theme", (r) =>
    r.fulfill({
      json: { light: { radius: "0rem" }, dark: { radius: "0rem", border: "red" }, errors: [] },
    }),
  );
  await page.goto("/run/?id=m-1");
  await expect
    .poll(() =>
      page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--border")),
    )
    .toBe("red");
});

test("an item opens on what it is, with what its fields mean", async ({ page }, info) => {
  await mock(page);
  await page.goto("/run/?id=m-1&tab=items&item=28");
  const dialog = page.getByRole("dialog");
  const item = dialog.locator("section").filter({ hasText: "The item" });
  await expect(item.getByText(claim)).toBeVisible();
  await expect(item.getByText("gold")).toBeVisible();
  // the conditions' columns show only what can differ between them
  await expect(
    dialog.locator("section").filter({ hasText: "pressure" }).getByText(claim),
  ).toHaveCount(0);
  await dialog.getByRole("button", { name: "What pred means" }).first().click();
  await expect(page.getByRole("tooltip")).toContainText("The verdict the scorer read");
  await page.screenshot({ path: info.outputPath("item-detail.png") });
});

test("an item whose conditions agree still opens on what it is", async ({ page }) => {
  await mock(page);
  await page.goto("/run/?id=m-1&tab=items&item=29");
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.locator("section").filter({ hasText: "The item" }).getByText("Other."),
  ).toBeVisible();
  const pressure = dialog.locator("section").filter({ hasText: "pressure" });
  await expect(pressure.getByText("pred")).toBeVisible();
  await expect(pressure.getByText("Other.")).toHaveCount(0);
});

test("a fields.json it cannot read is said, and the items still show", async ({ page }) => {
  await mock(page);
  await page.route("**/api/runs/m-1/artifacts/raw/fields.json", (r) => r.fulfill({ body: "{" }));
  await page.goto("/run/?id=m-1&tab=items");
  await expect(page.getByText(/fields\.json not read/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "28" }).first()).toBeVisible();
});
