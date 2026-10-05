import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// A mocked API: the Playground's research tools (pushback, patching, dose-response, speed) and
// the quality-against-cost scatter a grid logs.
async function mockPlayground(page: Page) {
  await page.route("**/api/playground", (r) =>
    r.fulfill({ json: { model: "tiny", layers: 2, heads: 4, bank: [], diffusion: false } }),
  );
  await page.route("**/api/vectors", (r) =>
    r.fulfill({
      json: [
        {
          name: "caving",
          model: "tiny",
          layer: 1,
          method: "diff-in-means",
          norm: 1,
          dim: 8,
          run: null,
          notes: null,
          created: "2026-10-03T00:00:00Z",
        },
      ],
    }),
  );
}

test("a follow-up pushes back on each side's own reply", async ({ page }, info) => {
  await mockPlayground(page);
  const sent: { prompt: string; history: { content: string }[]; interventions: unknown[] }[] = [];
  await page.route("**/api/playground/generate", (r) => {
    const body = r.request().postDataJSON();
    sent.push(body);
    const steered = body.interventions.length > 0;
    const text = body.history.length ? (steered ? " Yes, 4." : " You are right, it is 5.") : " 4";
    r.fulfill({ contentType: "text/plain", body: text });
  });
  await page.goto("/behavior/probe/");
  await page.getByLabel("Follow-up").fill("I think it's 5. Are you sure?");
  await page.getByLabel("Prompt", { exact: true }).fill("What is 2 + 2?");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("reply-base").getByTestId("follow-up")).toContainText("it is 5");
  await expect(page.getByTestId("reply-intervention").getByTestId("follow-up")).toContainText(
    "Yes, 4.",
  );
  const again = sent.filter((b) => b.history.length);
  expect(again).toHaveLength(2);
  expect(again.map((b) => b.history[1].content)).toEqual(["4", "4"]);
  expect(again[0].prompt).toBe("I think it's 5. Are you sure?");
  await page.screenshot({ path: info.outputPath("pushback.png"), fullPage: true });
});

test("patch, dose and speed send their requests and draw what comes back", async ({
  page,
}, info) => {
  await mockPlayground(page);
  const bodies: Record<string, Record<string, unknown>> = {};
  const heat = {
    kind: "heatmap",
    title: "Attribution patching: 'Paris' vs 'Rome'",
    x: ["0:The", "1:capital"],
    y: ["0", "1"],
    z: [
      [0.1, 0.9],
      [0, 1],
    ],
    x_label: "position",
    y_label: "layer",
  };
  const curve = {
    kind: "line",
    title: "Steering caving at layer 1: next-token log-probability",
    x: [-2, 0, 2],
    series: { "log p('Yes')": [-3, -1, -0.2] },
    x_label: "alpha",
    y_label: "log p",
  };
  const speedTable = {
    kind: "table",
    title: "Speed",
    columns: ["", "first token ms", "decode tok/s", "total s", "tokens", "peak MiB"],
    rows: [
      ["base", 12.5, 80.1, 0.81, 64, null],
      ["changed", 14.0, 71.3, 0.91, 64, null],
    ],
  };
  for (const [route, views] of [
    ["patch", [heat]],
    ["dose", [curve]],
    ["speed", [speedTable]],
  ] as const) {
    await page.route(`**/api/playground/${route}`, (r) => {
      bodies[route] = r.request().postDataJSON();
      r.fulfill({ json: { views } });
    });
  }
  await page.goto("/behavior/probe/?tab=patch");
  await page.getByLabel("Prompt", { exact: true }).fill("The capital of France is");
  await expect(page.getByRole("button", { name: /Run/ })).toBeDisabled();
  await page.getByLabel("Prompt", { exact: true }).press("Control+Enter");
  expect(bodies.patch).toBeUndefined(); // the shortcut waits for the same fields the button does
  await page.getByLabel("Corrupt prompt", { exact: true }).fill("The capital of Italy is");
  await page.getByLabel("Answer", { exact: true }).fill("Paris");
  await page.getByLabel("Foil", { exact: true }).fill("Rome");
  await page.getByRole("radio", { name: "attribution" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "residual" })).toBeFocused();
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByText(heat.title)).toBeVisible();
  expect(bodies.patch).toMatchObject({
    clean: "The capital of France is",
    corrupt: "The capital of Italy is",
    method: "residual",
  });
  await page.screenshot({ path: info.outputPath("patch.png"), fullPage: true });

  await page.getByRole("tab", { name: "Dose" }).click();
  await page.getByLabel("Answer", { exact: true }).fill("Yes");
  await page.getByLabel("Points", { exact: true }).fill("3");
  await page.getByLabel("α from").fill("-2");
  await page.getByLabel("α to").fill("2");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByText(curve.title)).toBeVisible();
  expect(bodies.dose).toMatchObject({ vector: "caving", layer: 1, alphas: [-2, 0, 2] });
  await page.screenshot({ path: info.outputPath("dose.png"), fullPage: true });

  // Speed is a cost, so it lives on Benchmark, under Efficiency.
  await page.goto("/efficiency/benchmark/");
  await expect(page.getByRole("tab", { name: "Speed" })).toHaveAttribute("data-state", "active");
  await expect(page.getByRole("tab", { name: "Patch" })).toHaveCount(0);
  await page.getByLabel("Prompt", { exact: true }).fill("The capital of France is");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByRole("cell", { name: "changed" })).toBeVisible();
  expect(bodies.speed).toMatchObject({ repeats: 3, interventions: [{ kind: "steer" }] });
  await page.screenshot({ path: info.outputPath("speed.png"), fullPage: true });
});

test("a grid's scatter plots each condition's score against its cost", async ({ page }, info) => {
  const run = {
    id: "m-1",
    kind: "analysis",
    name: "grid · accuracy",
    experiment: "attention-kernels",
    status: "finished",
    created: null,
    model: null,
    metrics: {},
    samples: null,
    params: {},
    tags: {},
    history: {},
    artifacts: [{ path: "views/04-grid.json", size: 1 }],
    scorers: [],
    error: null,
    log: null,
  };
  const scatter = {
    kind: "scatter",
    title: "accuracy against latency/mean",
    x_label: "latency/mean",
    y_label: "accuracy",
    points: [
      { label: "sdpa", x: 0.42, y: 0.71 },
      { label: "eager", x: 0.65, y: 0.71 },
      { label: "flex", x: 0.38, y: 0.69 },
    ],
    note: "means over seeds and samples",
  };
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: run }));
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/04-grid.json", view: scatter }] }),
  );
  await page.goto("/run/?id=m-1&tab=figures");
  const figure = page.locator("figure").filter({ hasText: scatter.title });
  await expect(figure.getByText("eager")).toBeVisible();
  await page.screenshot({ path: info.outputPath("scatter.png"), fullPage: true });
});

test("a diffusion model opens on Reply when the URL asks for a causal-only tab", async ({
  page,
}) => {
  await page.route("**/api/playground", (r) =>
    r.fulfill({ json: { model: "tiny", layers: 2, heads: null, bank: [], diffusion: true } }),
  );
  await page.route("**/api/vectors", (r) => r.fulfill({ json: [] }));
  await page.goto("/behavior/probe/?tab=patch");
  await expect(page.getByRole("tab", { name: "Reply" })).toHaveAttribute("data-state", "active");
  await expect(page.getByLabel("Corrupt prompt", { exact: true })).toHaveCount(0);
});
