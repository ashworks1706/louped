import type { Page } from "@playwright/test";

// One attribution graph over a mocked API, as louped's server scores it: "The capital of France
// is" → " Paris", through a France feature and a capital feature, with one error node.

const tokens = ["The", " capital", " of", " France", " is"];
const node = (
  id: string,
  kind: "embedding" | "feature" | "error" | "logit",
  layer: string,
  row: number,
  position: number,
  label: string,
  score: number,
  extra: Record<string, unknown> = {},
) => ({ id, kind, layer, row, position, feature: null, label, score, target: false, ...extra });

const nodes = [
  ...tokens.map((t, i) =>
    node(`E_${i}_${i}`, "embedding", "E", 0, i, t, [0.02, 0.2, 0.01, 0.35, 0.12][i]),
  ),
  node("0_11_3", "feature", "0", 1, 3, "France", 0.3, { feature: 11, activation: 4.2 }),
  node("0_12_1", "feature", "0", 1, 1, "capital", 0.18, { feature: 12, activation: 2.9 }),
  node("1_40_4", "feature", "1", 2, 4, "say a capital", 0.25, { feature: 40, activation: 3.1 }),
  node("1_3_3", "error", "1", 2, 3, "error at layer 1, ' France'", 0.06),
  node("2_7_4", "feature", "2", 3, 4, "say Paris", 0.55, { feature: 7, activation: 5.5 }),
  node("2_8_4", "feature", "2", 3, 4, "French things", 0.12, { feature: 8, activation: 1.2 }),
  node("4_9_4", "logit", "4", 4, 4, 'Output " Paris" (p=0.620)', 0.86, {
    prob: 0.62,
    target: true,
  }),
  node("4_5_4", "logit", "4", 4, 4, 'Output " the" (p=0.100)', 0.14, { prob: 0.1 }),
];
const link = (source: string, target: string, weight: number, share: number) => ({
  source,
  target,
  weight,
  share,
});
const links = [
  link("E_3_3", "0_11_3", 3.1, 0.3),
  link("E_1_1", "0_12_1", 2.2, 0.18),
  link("0_12_1", "1_40_4", 1.8, 0.16),
  link("E_4_4", "1_40_4", 0.9, 0.09),
  link("0_11_3", "2_7_4", 2.4, 0.3),
  link("1_40_4", "2_7_4", 1.6, 0.25),
  link("1_3_3", "2_7_4", 0.4, 0.06),
  link("0_11_3", "2_8_4", 0.8, 0.06),
  link("2_7_4", "4_9_4", 4.0, 0.55),
  link("2_8_4", "4_9_4", 0.7, 0.06),
  link("2_8_4", "4_5_4", -0.9, 0.06),
  link("E_0_0", "4_5_4", 0.3, 0.02),
  link("E_2_2", "4_5_4", -0.2, 0.01),
];

export const capital = {
  slug: "capital",
  prompt: tokens.join(""),
  tokens,
  scan: null,
  nodes,
  links,
  pinned: [],
  groups: [],
};

export async function mockCircuits(page: Page) {
  await page.route("**/api/graphs/capital", (r) => r.fulfill({ json: capital }));
  await page.route("**/api/graphs/capital/pins", (r) =>
    r.fulfill({ json: r.request().postDataJSON() }),
  );
}
