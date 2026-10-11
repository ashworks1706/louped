import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

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
    about: "What the model would predict if it stopped at each layer.",
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

// A readout of the same pass: 3 tokens, the embeddings and 2 layers, 4 heads.
const L = 3;
const by = <T>(f: (l: number, p: number) => T) =>
  Array.from({ length: L }, (_, l) => tokens.map((_, p) => f(l, p)));
function readout(shift = 0) {
  return {
    tokens,
    layers: ["emb", "0", "1"],
    vocab: { "1": "a", "2": "b", "3": "sure", "4": "no", "5": "ok", "6": "hm" },
    top_ids: by((l) => (l === 2 ? [3, 4, 5, 6, 1] : [1, 2, 3, 4, 5])),
    top_probs: by((l) => [0.3 + 0.3 * l, 0.1, 0.05, 0.03, 0.01]),
    entropy: by((l) => 3 - l),
    kl: by((l) => 2 - l),
    target: 3,
    target_prob: by((l) => Math.min(1, 0.05 + 0.4 * l + shift)),
    target_rank: by((l) => 2 - l),
    target_logit: [1, 2, 3],
    dla_embed: [0.1, 0.1, 0.2],
    dla_attn: [
      [0.5, 0.2, 1.5 + shift],
      [-0.2, 0.1, 0.4],
    ],
    dla_mlp: [
      [0.1, 0.3, 0.2],
      [0.3, -0.1, 0.7],
    ],
    dla_rest: [0.01, 0, -0.02],
    dla_heads: [0, 1].map((l) => [0, 1, 2, 3].map((h) => [0.1 * h, -0.1 * l, 0.4 * h - 0.2 * l])),
    head_positions: [0, 1, 2],
    head_entropy: [
      [1, 0.5, 0.2, 0.9],
      [0.3, 0.8, 1.1, 0.1],
    ],
    head_prev: [
      [0.9, 0.1, 0.2, 0.3],
      [0.1, 0.2, 0.1, 0.6],
    ],
    head_first: [
      [0.1, 0.8, 0.2, 0.3],
      [0.5, 0.2, 0.1, 0.1],
    ],
  };
}

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
  await page.goto("/behavior/probe/?tab=inspect");
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

test("Inspect's readout follows a token through the layers, heads and parts", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await mockApi(page);
  const asked: { target: string | null; target_id: number | null; interventions: unknown[] }[] = [];
  await page.route("**/api/playground/inspect", (r) => {
    const body = r.request().postDataJSON();
    asked.push(body);
    r.fulfill({ json: { views, readout: readout(body.interventions.length ? 0.2 : 0) } });
  });
  await page.goto("/behavior/probe/?tab=inspect");
  await page.getByLabel("Prompt").fill("hi");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("lens-cell")).toHaveCount(9);
  await expect(page.locator('[data-part="playground/readout/target"]')).toContainText(
    "p = 0.850, rank 1",
  );
  // the intervened pass follows the token the base pass followed
  expect(asked.find((b) => b.interventions.length)?.target_id).toBe(3);
  // the readout replaces the lens and attention figures; projections stay
  await expect(page.getByText("Projections", { exact: true })).toBeVisible();
  await expect(page.getByTestId("heat-cell")).toHaveCount(0);

  // a token moves every panel; a lens cell lists its top tokens; one of them becomes the target
  await page.getByRole("option", { name: "hi" }).click();
  await expect(page).toHaveURL(/lpos=1/);
  await page.getByRole("gridcell", { name: /layer 0, token 1/ }).click();
  await expect(page.locator('[data-part="playground/readout/cell"]')).toContainText(
    'layer 0 · token 1 "hi"',
  );
  await page
    .locator('[data-part="playground/readout/cell"]')
    .getByRole("button", { name: /"b"/ })
    .click();
  // a lens token is sent by its id; the intervened pass follows the base pass's target
  await expect.poll(() => asked.find((b) => b.target_id === 2) !== undefined).toBe(true);
  await expect(page).toHaveURL(/ltarget=%232/);

  // a head shows what the picked token reads through it
  await page.getByLabel("Score heads by").selectOption("prev");
  await expect(page.getByTestId("head-cell")).toHaveCount(8);
  await page.getByRole("gridcell", { name: /layer 0 head 0/ }).click();
  await expect(page.locator('[data-part="playground/readout/head"]')).toContainText(
    "previous 0.90",
  );
  await page.screenshot({ path: info.outputPath("readout.png"), fullPage: true });

  // the intervened side shows the change from base
  await page.getByRole("tab", { name: /ablate|steer/ }).click();
  await expect(page.getByText("Δ target probability")).toBeVisible();
  await page.screenshot({ path: info.outputPath("readout-delta.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("every figure says how to read it behind its ?", async ({ page }) => {
  await mockApi(page);
  await page.goto("/behavior/probe/?tab=inspect");
  await page.getByLabel("Prompt").fill("hi");
  await page.getByRole("button", { name: /Run/ }).click();
  // a tap opens it, so it works without hover too
  await page.getByRole("button", { name: "How to read Logit lens" }).click();
  await expect(page.getByRole("tooltip")).toContainText("if it stopped at each layer");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  // a figure logged without its own explanation gets its kind's
  await page.getByRole("button", { name: "How to read Projections" }).click();
  await expect(page.getByRole("tooltip")).toContainText("Each token is shaded");
});

test("Reply tab shows both streamed replies", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/playground/generate", (r) =>
    r.fulfill({
      contentType: "text/plain",
      body: r.request().postDataJSON().interventions.length ? " steered reply" : " base reply",
    }),
  );
  await page.goto("/behavior/probe/");
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
  await page.goto("/behavior/probe/");
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
  await page.goto("/behavior/probe/");
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
