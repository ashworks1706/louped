import { expect, test } from "./fixtures";
import { mock, run } from "./items-run";
import { mockReports } from "./reports-api";
import { mockSources } from "./sources-api";

// reports/: listed, read as they will be read, and filled by exporting figures.

test("reports are listed and a write-up renders with its citations", async ({ page }, info) => {
  await mock(page);
  await mockSources(page);
  await mockReports(page);
  await page.goto("/reports/");
  const figure = page.locator('[data-part="reports/report/figures%2Fbars.svg"]');
  await expect(figure).toContainText("run:m-1/views/bars.json");
  await expect(page.locator('[data-part="reports/heading"]')).toHaveText("4 files");
  await page.screenshot({ path: info.outputPath("reports.png") });
  await page.getByRole("link", { name: "1b.md" }).click();
  await expect(page).toHaveURL(/\/report\/\?path=1b\.md/);
  await expect(page.locator('[data-cite="pushback"]')).toHaveText("pushback p1");
});

test("a PDF report turns its pages and a figure shows as it is", async ({ page }) => {
  await mock(page);
  await mockReports(page);
  await page.goto("/report/?path=paper.pdf");
  await expect(page.locator(".pdf-page .textLayer span", { hasText: "Page one" })).toBeVisible();
  await expect(page.locator('[data-part="report/controls"]')).toContainText("1 / 3");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.locator(".pdf-page .textLayer span", { hasText: "Page two" })).toBeVisible();
  await page.goto("/report/?path=figures%2Fbars.svg");
  await expect(
    page.getByRole("img", { name: "Figure exported from run:m-1/views/bars.json" }),
  ).toBeVisible();
  await expect(page.locator('[data-part="report/header"]')).toContainText(
    "Exported from run:m-1/views/bars.json",
  );
});

test("a deck shows as LibreOffice prints it, or as its text saying why", async ({ page }) => {
  await mock(page);
  await mockReports(page);
  await page.goto("/report/?path=lab.pptx");
  await expect(page.locator('[data-part="report/note"]')).toContainText(
    "LibreOffice is not installed",
  );
  await expect(page.locator('[data-part="report/block/1"]')).toContainText("Slide 1");
  await expect(page.locator('[data-part="report/block/3"]')).toContainText("Evidence helps");
  await expect(page.locator('[data-part="report/block/2"]')).toHaveCount(0); // an empty slide
  await page.unrouteAll();
  await mock(page);
  await mockReports(page, true);
  await page.reload();
  await expect(page.locator(".pdf-page .textLayer span", { hasText: "Caving rate" })).toBeVisible();
  await expect(page.locator('[data-part="report/controls"]')).toContainText("1 / 2");
});

test("a figure exports to reports/ from a run's Figures tab", async ({ page }) => {
  await mock(page);
  await mockReports(page);
  const chart = {
    kind: "vega",
    title: "Caving by condition",
    spec: {
      mark: "bar",
      data: { values: [{ c: "pressure", v: 0.9 }] },
      encoding: { x: { field: "c", type: "nominal" }, y: { field: "v", type: "quantitative" } },
    },
  };
  await page.route("**/api/runs/m-1", (r) =>
    r.fulfill({
      json: { ...run, artifacts: [...run.artifacts, { path: "views/bars.json", size: 1 }] },
    }),
  );
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/bars.json", view: chart }] }),
  );
  const sent: { replace: boolean }[] = [];
  await page.route("**/api/reports/figures", (r) => {
    const body = r.request().postDataJSON() as { replace: boolean };
    sent.push(body);
    if (!body.replace)
      return r.fulfill({
        status: 409,
        json: { detail: "reports/figures/m-1-bars.png exists: replace it, or give a name" },
      });
    return r.fulfill({
      json: {
        path: "figures/m-1-bars.png",
        kind: "png",
        size: 1,
        modified: "2026-10-05T12:00:00Z",
        ref: "run:m-1/views/bars.json",
      },
    });
  });
  await page.goto("/run/?id=m-1&tab=figures");
  await page
    .getByRole("group", { name: "Export figure" })
    .getByRole("button", { name: "PNG" })
    .click();
  // a file of the same name is replaced only when asked
  await expect(page.getByText("m-1-bars.png exists")).toBeVisible();
  await page.getByRole("button", { name: "Replace" }).click();
  const ref = "run:m-1/views/bars.json";
  await expect
    .poll(() => sent)
    .toEqual([
      { ref, format: "png", replace: false },
      { ref, format: "png", replace: true },
    ]);
  await expect(page.getByText("Exported to reports/figures/m-1-bars.png")).toBeVisible();
});
