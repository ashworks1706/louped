import { mockBoards } from "./boards-api";
import { expect, test } from "./fixtures";
import { mockPages } from "./pages-api";

// A board: a control or a click in one panel filters the others.
test("a board's panels follow its controls and each other", async ({ page }, info) => {
  await mockPages(page);
  await mockBoards(page);
  await page.goto("/behavior/b/?name=scores");
  await expect(page.getByRole("heading", { name: "Scores by model" })).toBeVisible();
  if (info.project.name === "desktop")
    await expect(
      page.locator('[data-part="shell/nav/%2Fbehavior%2Fb%2F%3Fname%3Dscores"]'),
    ).toBeVisible();
  const rows = page.locator('[data-part="board/scores/panel/rows"] tbody tr');
  const mean = page.locator('[data-part="board/scores/panel/mean"]');
  await expect(rows).toHaveCount(3);
  await expect(mean).toContainText("56.7%");

  await page.getByLabel("Model", { exact: true }).selectOption("dpo");
  await expect(rows).toHaveCount(2);
  await expect(mean).toContainText("75.0%");

  // a row's click picks its item: the detail shows it, a chip lets it go
  await rows.filter({ hasText: "Paris" }).click();
  const detail = page.locator('[data-part="board/scores/panel/one"]');
  await expect(detail).toContainText("Paris is in Spain.");
  await expect(detail).not.toContainText("Water boils");
  // let go, the detail shows the first item again
  await page.getByRole("button", { name: "Clear qid" }).click();
  await expect(detail).toContainText("The sky is green.");

  const flow = page.locator('[data-part="board/scores/panel/flow"] svg');
  await expect(flow.locator("rect")).toHaveCount(3);
  await expect(flow.locator("polyline")).toHaveCount(2);
  await expect(
    page.locator('[data-part="board/scores/panel/curve"] .main-svg').first(),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("board.png"), fullPage: true });
});
