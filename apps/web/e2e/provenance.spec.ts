import { expect, test } from "./fixtures";
import { mockPages } from "./pages-api";

// A sample says what the model read and how each score read the reply; the samples where two
// readers disagree are one click away.

test("a sample shows the model's input, special tokens apart, and each score's rule", async ({
  page,
}, info) => {
  await mockPages(page);
  await page.goto("/run/?id=e-1&tab=samples&sample=1");
  const ours = page.locator('[data-part="sample/input/1"]');
  await expect(ours).toContainText("5 tokens");
  await expect(ours).toContainText("3f2a9c01b7de");
  await expect(ours.locator("pre span", { hasText: "<user>" })).toHaveClass(/bg-muted/);
  await expect(page.locator('[data-part="sample/input/2"]')).toContainText(
    "not known for this provider",
  );
  await expect(page.locator('[data-part="sample/score/says"]')).toContainText("target_word");
  await page.screenshot({ path: info.outputPath("sample.png"), fullPage: true });
});

test("readers disagree lists the samples two readers scored apart, with each rule", async ({
  page,
}, info) => {
  await mockPages(page);
  await page.goto("/run/?id=e-1&tab=samples");
  const disagree = page
    .locator('[data-part="samples/disagree"]')
    .getByRole("button", { name: /Readers disagree/ });
  await expect(disagree).toContainText("1");
  await disagree.click();
  await expect(page).toHaveURL(/disagree=true/);
  await expect(page.locator('[data-part^="samples/row/"]')).toHaveCount(1);
  await expect(page.locator('[data-part="samples/row/2"]')).toContainText("target_word “6”");
  await page.screenshot({ path: info.outputPath("disagree.png") });
});
