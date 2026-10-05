import { expect, test } from "./fixtures";
import { mockPages } from "./pages-api";

// What the tools find lands beside the experiments: a Probe result kept as a run, how alike the
// saved vectors are, and two trainings' curves on one chart.
const lens = {
  kind: "heatmap",
  title: "Logit lens",
  x: ["0:hi"],
  y: ["emb", "0"],
  z: [[0.1], [0.9]],
  x_label: "position",
  y_label: "layer",
};

test("a Probe result is kept as a run under an experiment", async ({ page }, info) => {
  await mockPages(page);
  await page.route("**/api/playground/inspect", (r) => r.fulfill({ json: { views: [lens] } }));
  let sent: Record<string, unknown> | undefined;
  await page.route("**/api/playground/save", (r) => {
    sent = r.request().postDataJSON();
    return r.fulfill({ json: { run: "m-1" } });
  });
  await page.goto("/behavior/probe/?tab=inspect&mode=heads&heads=");
  const save = page.locator('[data-part="playground/save"]');
  await expect(save).toBeDisabled();
  await page.getByLabel("Prompt").fill("hi");
  await page.getByRole("button", { name: /^Run/ }).click();
  await expect(page.locator('[data-part="playground/figure/logit-lens"]')).toBeVisible();
  await save.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Experiment").selectOption("hello");
  await page.screenshot({ path: info.outputPath("save.png") });
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => sent?.experiment).toBe("hello");
  expect(sent).toMatchObject({ tool: "inspect", prompt: "hi", label: "no intervention" });
  expect((sent!.views as { title: string }[]).map((v) => v.title)).toEqual(["Logit lens"]);
  await page.getByRole("button", { name: "Open" }).click();
  await expect(page).toHaveURL(/\/run\/\?id=m-1/);
});

test("Vectors says how alike a model's vectors are", async ({ page }, info) => {
  await mockPages(page);
  await page.goto("/behavior/vectors/");
  const alike = page.locator('[data-part="vectors/similar/tiny"]');
  await expect(alike).toContainText("How alike they are");
  await expect(alike.getByTestId("heat-cell").nth(1)).toHaveText("0.12");
  await page.screenshot({ path: info.outputPath("vectors.png"), fullPage: true });
});

test("Compare lays two trainings' curves over each other", async ({ page }, info) => {
  await mockPages(page);
  await page.goto("/compare/?a=t-1&b=t-2");
  const curves = page.locator('[data-part="compare/section/curves"]');
  await expect(curves.locator('[data-part="curves/metric/loss"]')).toContainText("A dashed");
  await expect(curves.locator(".recharts-line")).toHaveCount(2);
  await page.screenshot({ path: info.outputPath("curves.png"), fullPage: true });
});
