import { expect, test } from "./fixtures";
import { mock, run } from "./items-run";
import { mockSources, paper, pinned } from "./sources-api";

// The project's sources: searched, read page by page, pinned and cited.

test("sources are searched and listed", async ({ page }, info) => {
  await mock(page);
  await mockSources(page);
  await page.goto("/sources/");
  await expect(page.locator('[data-part="sources/source/pushback"]')).toContainText("pdf");
  await page.getByRole("searchbox").fill("pushback");
  await expect(page).toHaveURL(/q=pushback/);
  const hit = page.locator('[data-part="sources/hit/pushback/1"]');
  await expect(hit.locator("mark")).toHaveText("pushback");
  await page.screenshot({ path: info.outputPath("sources.png") });
  await hit.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/source\/\?key=pushback&page=1/);
});

test("a PDF is drawn, its pins marked, and selected words are pinned", async ({ page }, info) => {
  await mock(page);
  await mockSources(page);
  const sent: unknown[] = [];
  await page.route("**/api/pins", (r) => {
    sent.push(r.request().postDataJSON());
    return r.fulfill({ json: pinned });
  });
  await page.goto("/source/?key=pushback");
  await expect(page.getByRole("heading", { name: paper.title })).toBeVisible();
  const words = page.locator(".pdf-page .textLayer span", { hasText: "pushback" });
  await expect(words).toBeVisible();
  await expect(words).toHaveClass(/pinned/);
  const pins = page.locator('[data-part="source/pins"]');
  await expect(pins).toContainText("cave to pushback");
  await expect(pins).toContainText("[@pushback p1]");
  await page.screenshot({ path: info.outputPath("pdf.png") });

  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page).toHaveURL(/page=2/);
  const evidence = page.locator(".pdf-page .textLayer span", { hasText: "Evidence" });
  await expect(evidence).toBeVisible();
  await expect(evidence).not.toHaveClass(/pinned/);
  await expect(page.getByRole("button", { name: "Pin", exact: true })).toBeDisabled();
  await evidence.selectText();
  await page.getByRole("textbox", { name: "Note for the pin" }).fill("why evidence helps");
  await page.getByRole("button", { name: "Pin", exact: true }).click();
  await expect
    .poll(() => sent)
    .toEqual([
      {
        key: "pushback",
        page: 2,
        quote: "Evidence helps them",
        note: "why evidence helps",
        links: [],
      },
    ]);
});

test("a slide is shown as its text", async ({ page }) => {
  await mock(page);
  await mockSources(page);
  await page.goto("/source/?key=deck");
  await expect(page.locator('[data-part="source/page"]')).toHaveText("Caving rate by condition");
  await expect(page.locator('[data-part="source/pins"]')).toContainText("[@deck p<page>]");
});

test("a notebook shows cell by cell, then whole in a frame that runs no scripts", async ({
  page,
}) => {
  await mock(page);
  await mockSources(page);
  await page.goto("/source/?key=explore");
  await expect(page.locator('[data-part="source/page"]')).toHaveText("n = 2");
  const frame = page.locator('[data-part="source/notebook"] iframe');
  await expect(frame).toHaveAttribute("sandbox", "");
  await expect(
    page.frameLocator('[data-part="source/notebook"] iframe').getByText("printed 4"),
  ).toBeVisible();
});

test("a run's notebook shows as Jupyter does, in a frame that runs no scripts", async ({
  page,
}) => {
  await mock(page);
  const file = { path: "notebook/explore.ipynb", size: 10 };
  await page.route("**/api/runs/m-1", (r) =>
    r.fulfill({ json: { ...run, artifacts: [...run.artifacts, file] } }),
  );
  const asked: string[] = [];
  await page.route("**/api/runs/m-1/notebook/notebook/explore.ipynb?*", (r) => {
    asked.push(new URL(r.request().url()).searchParams.get("theme") ?? "");
    return r.fulfill({
      body: '<html><body><main class="jp-Notebook"><p>printed 9</p></main></body></html>',
      contentType: "text/html",
    });
  });
  await page.goto("/run/?id=m-1&tab=artifacts&file=notebook%2Fexplore.ipynb");
  const frame = page.locator('iframe[title="notebook/explore.ipynb"]');
  await expect(frame).toHaveAttribute("sandbox", "");
  await expect(
    page.frameLocator('iframe[title="notebook/explore.ipynb"]').getByText("printed 9"),
  ).toBeVisible();
  expect(asked[0]).toMatch(/^(light|dark)$/);
});

test("a citation in Markdown names the passage it rests on", async ({ page }) => {
  await mock(page);
  await mockSources(page);
  await page.route("**/api/experiments/hello", (r) =>
    r.fulfill({
      json: {
        name: "hello",
        axis: "behavior",
        domain: "honesty",
        domain_title: "Honesty",
        status: "active",
        question: "Does pushback flip answers?",
        result: null,
        runs: [],
        readme: "# hello\n\n## Question\n\nModels cave [@pushback p1], and [@nope p2].\n",
      },
    }),
  );
  await page.goto("/behavior/experiment/?name=hello");
  const cite = page.locator('[data-cite="pushback"]');
  await expect(cite).toHaveText("pushback p1");
  await cite.hover();
  await expect(page.getByRole("tooltip")).toContainText(pinned.exact);
  await expect(page.locator('[data-cite="nope"]')).toHaveText("nope p2");
  await cite.click();
  await expect(page).toHaveURL(/\/source\/\?key=pushback&page=1/);
});
