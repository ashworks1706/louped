import { expect, test } from "@playwright/test";

// Mocked API: the viewers louped embeds (Inspect View, Neuronpedia, circuit-tracer) as iframes.
const run = {
  id: "e-1",
  kind: "eval",
  name: "task",
  experiment: null,
  status: "success",
  created: null,
  model: "louped/tiny",
  metrics: {},
  samples: 1,
  params: {},
  tags: {},
  history: {},
  artifacts: [{ path: "views/sae.json", size: 1 }],
  scorers: [],
  error: null,
  log: "2026_task.eval",
};

test("an eval run opens its log in Inspect View, at the sample", async ({ page }, info) => {
  await page.route("**/api/runs/e-1", (r) => r.fulfill({ json: run }));
  await page.route("**/api/runs/e-1/samples", (r) =>
    r.fulfill({ json: [{ id: "7", epoch: 1, input: "hi", target: "", scores: {}, error: null }] }),
  );
  await page.route("**/api/runs/e-1/samples/7*", (r) =>
    r.fulfill({
      json: { id: "7", epoch: 1, target: "", messages: [], scores: [], metadata: {}, error: null },
    }),
  );
  await page.route("**/inspect/**", (r) => r.fulfill({ body: "<title>Inspect View</title>" }));
  await page.goto("/run/?id=e-1&tab=samples&sample=7");
  await page.getByRole("button", { name: "Log" }).click();
  const frame = page.getByTitle("Inspect View");
  await expect(frame).toBeVisible();
  await expect(frame).toHaveAttribute("src", /#\/logs\/2026_task\.eval\/samples\/sample\/7\/1\/$/);
  await page.screenshot({ path: info.outputPath("log.png"), fullPage: true });
});

test("a Neuronpedia feature opens embedded beside the table", async ({ page }, info) => {
  const table = {
    kind: "table",
    title: "SAE features",
    columns: ["token", "top 1"],
    rows: [["hi", "#12 3.0"]],
    links: [[null, "https://neuronpedia.org/gemma-2-2b/20-gemmascope-res-16k/12"]],
    embed: "neuronpedia",
  };
  await page.route("**/api/runs/e-1", (r) => r.fulfill({ json: run }));
  await page.route("**/api/runs/e-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/sae.json", view: table }] }),
  );
  await page.route("https://neuronpedia.org/**", (r) => r.fulfill({ body: "feature" }));
  await page.goto("/run/?id=e-1&tab=figures");
  const cell = page.getByRole("button", { name: "#12 3.0" });
  await cell.click();
  await expect(page.getByTitle(/^Neuronpedia feature/)).toHaveAttribute("src", /\/12\?embed=true$/);
  await page.screenshot({ path: info.outputPath("neuronpedia.png") });
  await expect(page.getByRole("link", { name: "Open in a new tab" })).toHaveAttribute(
    "href",
    table.links[0][1] as string,
  );
  await page.getByRole("button", { name: "Close" }).click();
  await expect(cell).toBeFocused();
});

test("circuits shows the latest graph in circuit-tracer's viewer", async ({ page }, info) => {
  await page.route("**/api/graphs", (r) =>
    r.fulfill({
      json: [
        { slug: "a", prompt: "first", scan: null },
        { slug: "capital", prompt: "The capital of France is", scan: null },
      ],
    }),
  );
  await page.route("**/circuit/**", (r) =>
    r.fulfill({ body: "<title>Attribution Graphs</title>" }),
  );
  await page.goto("/behavior/circuits/");
  await expect(page.getByTitle("Attribution graph capital")).toHaveAttribute(
    "src",
    /\/circuit\/\?slug=capital$/,
  );
  await page.getByLabel("Graph").selectOption("a");
  await expect(page).toHaveURL(/slug=a/);
  await expect(page.getByTitle("Attribution graph a")).toBeVisible();
  await page.screenshot({ path: info.outputPath("circuits.png"), fullPage: true });
});
