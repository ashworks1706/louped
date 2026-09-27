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

async function mockApi(page: Page, info: object = {}) {
  await page.route("**/api/playground", (r) =>
    r.fulfill({
      json: { model: "tiny", layers: 1, heads: 4, bank: [], diffusion: false, ...info },
    }),
  );
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

test("Reply tab shows both streamed replies", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/playground/generate", (r) =>
    r.fulfill({
      contentType: "text/plain",
      body: r.request().postDataJSON().interventions.length ? " steered reply" : " base reply",
    }),
  );
  await page.goto("/playground/");
  await page.getByLabel("Prompt").fill("hi");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("reply-base")).toContainText("base reply");
  await expect(page.getByTestId("reply-intervention")).toContainText("steered reply");
  await expect(page.getByRole("button", { name: /Run/ })).toBeEnabled();
});

test("Adapters and heads go to the intervened side and into the model args", async ({
  page,
}, info) => {
  await mockApi(page, { layers: 2, bank: ["formal", "terse"] });
  const sent: { adapters: string[]; interventions: { kind: string; heads: number[] }[] }[] = [];
  await page.route("**/api/playground/generate", (r) => {
    sent.push(r.request().postDataJSON());
    r.fulfill({
      contentType: "text/plain",
      body: sent.at(-1)!.adapters.length ? " terse" : " base",
    });
  });
  await page.goto("/playground/");
  await page.getByRole("checkbox", { name: "terse" }).click();
  await page.getByRole("radio", { name: "heads" }).click();
  await page.getByLabel("Heads").fill("1, 3, 9");
  await expect(page.getByText(`-M adapters='["terse"]'`)).toBeVisible();
  await page.getByLabel("Prompt").fill("hi");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("reply-intervention")).toContainText("terse");
  const edited = sent.find((b) => b.adapters.length)!;
  expect(edited.adapters).toEqual(["terse"]);
  expect(edited.interventions[0]).toMatchObject({ kind: "heads", heads: [1, 3] });
  await page.screenshot({ path: info.outputPath("bank.png"), fullPage: true });
});

test("A diffusion model denoises and shows its trajectory", async ({ page }, info) => {
  await mockApi(page, { heads: null, bank: ["skill"], diffusion: true });
  await page.route("**/api/playground/generate", (r) =>
    r.fulfill({ contentType: "text/plain", body: "the sky is blue" }),
  );
  const trajectory = {
    kind: "heatmap",
    title: "Denoising trajectory",
    x: ["0", "1"],
    y: ["0", "1"],
    z: [
      [0, 0.9],
      [0.4, 0],
    ],
    x_label: "reply position",
    y_label: "step",
    labels: [
      ["", "blue"],
      ["sky", "blue"],
    ],
  };
  await page.route("**/api/playground/inspect", (r) =>
    r.fulfill({ json: { views: [trajectory] } }),
  );
  await page.goto("/playground/");
  await expect(page.getByRole("radiogroup")).toHaveCount(0);
  await page.getByLabel("Steps").fill("8");
  await expect(page.getByText(`-M diffusion='{"length":64,"steps":8}'`)).toBeVisible();
  await page.getByLabel("Prompt").fill("what is the sky");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("reply-base")).toContainText("the sky is blue");
  await page.getByRole("tab", { name: "Inspect" }).click();
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("heat-cell").filter({ hasText: "sky" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("diffusion.png"), fullPage: true });
});
