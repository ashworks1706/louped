import { gsm8k } from "./datasets-api";
import { expect, test } from "./fixtures";
import { mockPages } from "./pages-api";

// The Datasets pages: each domain lists its datasets and those filed under none; a dataset opens
// with its card, splits, features and first rows; the Hub is searched and added from here.
test("each domain lists its datasets, and one opens with its rows", async ({ page }, info) => {
  await mockPages(page);
  const asked: string[] = [];
  page.on("request", (r) => r.url().includes("/api/datasets/hub") && asked.push(r.url()));
  await page.goto("/behavior/datasets/");
  await expect(page.getByRole("heading", { level: 1, name: "Datasets" })).toBeVisible();
  const rows = page.locator('[data-part^="datasets/row/"]');
  await expect(rows).toHaveCount(4);
  await expect(page.locator('[data-part="datasets/heading"]')).toHaveText("4 datasets");
  // a training set opens on its own page
  await expect(page.getByRole("link", { name: "pushback.jsonl" })).toHaveAttribute(
    "href",
    "/behavior/training-sets/?set=%2Fhome%2Fme%2F.louped%2Fdata%2Fpushback%2Fpushback.jsonl",
  );
  await page.screenshot({ path: info.outputPath("datasets.png"), fullPage: true });

  await page.locator('[data-part="datasets/row/openai%2Fgsm8k"]').click();
  await expect(page).toHaveURL(/open=openai(%2F|\/)gsm8k/);
  const facts = page.locator('[data-part="datasets/detail/facts"]');
  await expect(facts).toContainText("mit");
  await expect(facts).toContainText("7.5K");
  await expect(page.locator('[data-part="datasets/detail/features"]')).toContainText("question");
  await expect(page.locator('[data-part^="datasets/sample/"]')).toHaveCount(2);
  await expect(page.getByText("Natalia sold clips")).toBeVisible();
  await expect(page.locator('[data-part="datasets/detail/card"]')).toContainText("Grade school");
  await page.waitForTimeout(300); // the panel slides in
  await page.screenshot({ path: info.outputPath("dataset-open.png") });

  await page
    .getByLabel("Split", { exact: true })
    .selectOption({ label: "main / test · 1.3K rows" });
  await expect(page).toHaveURL(/split=test/);
  await expect.poll(() => asked.some((u) => u.includes("split=test"))).toBe(true);

  // Efficiency lists those filed under it or under none: not gsm8k
  await page.goto("/efficiency/datasets/");
  await expect(page.locator('[data-part^="datasets/row/"]')).toHaveCount(3);
  await expect(page.locator('[data-part="datasets/row/openai%2Fgsm8k"]')).toHaveCount(0);
});

test("a dataset found on the Hub is added to this domain, or downloaded", async ({ page }) => {
  await mockPages(page);
  const hit = { ...gsm8k.hub, id: "allenai/ai2_arc", url: "https://huggingface.co/datasets/x" };
  await page.route("**/api/hub/search?*", (r) => r.fulfill({ json: [hit] }));
  const sent: unknown[] = [];
  await page.route("**/api/hub/add", (r) => {
    const body = r.request().postDataJSON();
    sent.push(body);
    const job = body.download
      ? { id: "j1", title: "louped hub get openai/gsm8k --dataset", argv: [], status: "queued",
          created: "2026-10-11T00:00:00Z", started: null, ended: null, exit_code: null } // prettier-ignore
      : null;
    return r.fulfill({
      json: { added: { models: [], embeddings: [], datasets: [] }, source: null, job },
    });
  });
  await page.goto("/efficiency/datasets/");
  await page.getByLabel("Search datasets on the Hub").fill("arc");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/q=arc/);
  await page.locator('[data-part="datasets/add/allenai%2Fai2_arc"]').click();
  await expect
    .poll(() => sent)
    .toEqual([{ kind: "datasets", id: "allenai/ai2_arc", domains: ["efficiency"] }]);
  await expect(page.locator('[data-part="datasets/add/allenai%2Fai2_arc"]')).toHaveText("Added");

  await page.goto("/behavior/datasets/?open=openai%2Fgsm8k");
  await page.locator('[data-part="datasets/detail/download"]').click();
  await expect(page).toHaveURL(/\/job\/\?id=j1/); // a download is a job, followed on its page
  expect(sent.at(-1)).toEqual({
    kind: "datasets",
    id: "openai/gsm8k",
    download: true,
    domains: [],
  });
});

test("what the viewer cannot read is said, and an empty page says what fills it", async ({
  page,
}, info) => {
  await mockPages(page);
  await page.route("**/api/datasets/hub?*", (r) =>
    r.fulfill({
      json: {
        ...gsm8k,
        rows: [],
        features: [],
        splits: [],
        total: null,
        error: "the dataset viewer answered 501 for /splits: not available for this dataset.",
      },
    }),
  );
  await page.goto("/behavior/datasets/?open=cais%2Fmmlu");
  await expect(page.locator('[data-part="datasets/detail/error"]')).toContainText(
    "answered 501 for /splits",
  );
  await expect(page.locator('[data-part="datasets/detail/add"]')).toHaveCount(0); // listed already
  await page.screenshot({ path: info.outputPath("dataset-error.png") });

  await page.route("**/api/datasets", (r) => r.fulfill({ json: [] }));
  await page.goto("/behavior/datasets/");
  await expect(page.getByRole("heading", { name: "No datasets here yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Browse the Hub" })).toHaveAttribute(
    "href",
    "/hub/?kind=datasets",
  );
});
