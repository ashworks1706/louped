import { expect, test, type Page } from "@playwright/test";

// A mocked API: the Playground's Inspect tab against one lens, projection and attention view.
const tokens = ["<user>", "hi", "<assistant>"];
const grid = [
  [1, 0, 0],
  [0.5, 0.5, 0],
  [0.2, 0.7, 0.1],
];
const views = [
  {
    kind: "heatmap",
    title: "Logit lens",
    x: tokens.map((t, i) => `${i}:${t}`),
    y: ["emb", "0"],
    z: [
      [0.1, 0.2, 0.3],
      [0.4, 0.5, 0.9],
    ],
    x_label: "position",
    y_label: "layer",
    labels: [
      ["a", "b", "c"],
      ["d", "e", "sure"],
    ],
  },
  {
    kind: "tokens",
    title: "Projections",
    rows: [{ tokens, values: { refusal: [0.1, -2, 3] } }],
  },
  {
    kind: "tokens",
    title: "Attention",
    rows: [{ tokens, values: { "layer 0 · head 0": grid[2] } }],
    pairs: { "layer 0 · head 0": grid },
  },
];

async function mockApi(page: Page) {
  await page.route("**/api/playground", (r) => r.fulfill({ json: { model: "tiny", layers: 1 } }));
  await page.route("**/api/vectors", (r) =>
    r.fulfill({
      json: [
        {
          name: "refusal",
          model: "tiny",
          layer: 0,
          method: "diff-in-means",
          norm: 1,
          dim: 8,
          run: null,
          notes: null,
          created: "2026-09-27T00:00:00Z",
        },
      ],
    }),
  );
  await page.route("**/api/playground/inspect", (r) => r.fulfill({ json: { views } }));
}

test("Inspect tab draws the lens, projections and attention", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await mockApi(page);
  await page.goto("/playground/?tab=inspect");
  await page.getByLabel("Prompt").fill("hi");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByText("Logit lens", { exact: true })).toBeVisible();
  await expect(page.getByTestId("heat-cell").filter({ hasText: "sure" })).toBeVisible();

  const attention = page.locator("figure").filter({ hasText: "Attention" });
  const text = attention.getByLabel(/arrow keys/);
  await text.focus();
  await expect(attention.getByText(/query 2 "<assistant>"/)).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Enter");
  // query 1 is picked: its row [0.5, 0.5, 0] colours the text, the cursor reads the weight
  await expect(attention.getByText('1 "hi": 0.500')).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await expect(attention.getByText('0 "<user>": 0.500')).toBeVisible();
  await expect(attention.getByTestId("heat-cell")).toHaveCount(9);

  await page.getByRole("tab", { name: /ablate|steer/ }).click();
  await expect(page).toHaveURL(/side=intervention/);
  await page.screenshot({ path: info.outputPath("inspect.png"), fullPage: true });
  expect(errors).toEqual([]);
});
