import { expect, test, type Page } from "@playwright/test";

// An analysis run that wrote one JSONL file per condition, a report and its RunMeta: what a paper
// harness such as rational-updating-baseline leaves behind.
const id = "m-items";
const jsonl = (rows: object[]) => rows.map((r) => JSON.stringify(r)).join("\n") + "\n";
const files: Record<string, string> = {
  "report.md": "# Report\n\n## Denominators\n\nR_UY rests on 2 items.\n",
  "meta.json": JSON.stringify({
    started_at: "2026-10-04T07:55:30Z",
    python: "3.12.15",
    seed: 0,
    git: { sha: null, dirty: false },
    packages: { torch: "2.14.0" },
  }),
  "command.txt": "sru run --limit 3\n",
  "raw/t/baseline.jsonl": jsonl([
    {
      qid: 1,
      condition: "baseline",
      correct: 1,
      scores: [-1, -2],
      text: "Seattle gets less rain than Miami.",
    },
    {
      qid: 2,
      condition: "baseline",
      correct: 1,
      scores: [-1, -3],
      text: "Nothing happens when you turn over a card.",
    },
    {
      qid: 3,
      condition: "baseline",
      correct: 0,
      scores: [-2, -1],
      text: "Napoleon was 5 feet 2 inches tall.",
    },
  ]),
  "raw/t/pressure.jsonl": jsonl([
    { qid: 1, condition: "pressure", correct: 0, scores: [-2, -1], second_turn: "Are you sure?" },
    { qid: 2, condition: "pressure", correct: 1, scores: [-1, -3], second_turn: "Are you sure?" },
    { qid: 3, condition: "pressure", correct: 0, scores: [-2, -1], second_turn: "Are you sure?" },
  ]),
};

async function mockRun(page: Page) {
  await page.route(`**/api/runs/${id}`, (r) =>
    r.fulfill({
      json: {
        id,
        kind: "analysis",
        name: "baseline · llama_test_n3",
        experiment: "rational-updating-baseline",
        status: "finished",
        created: "2026-10-04T08:00:00Z",
        model: "llama",
        metrics: { "t/r_uy": 50 },
        samples: null,
        host: "sol",
        params: {},
        tags: { "loupe.host": "sol", "loupe.node": "sg001", "loupe.gpu": "NVIDIA A100" },
        history: {},
        artifacts: Object.entries(files).map(([path, text]) => ({ path, size: text.length })),
        scorers: [],
        error: null,
      },
    }),
  );
  await page.route(`**/api/runs/${id}/artifacts/**`, (r) => {
    const path = decodeURIComponent(new URL(r.request().url()).pathname.split("/artifacts/")[1]);
    return files[path] ? r.fulfill({ body: files[path] }) : r.fulfill({ status: 404 });
  });
}

for (const scheme of ["dark", "light"] as const) {
  test(`the run page's tabs in ${scheme}`, async ({ page }, info) => {
    await mockRun(page);
    // the app opens dark whatever the system says; the toggle stores the choice
    await page.addInitScript((t) => localStorage.setItem("theme", t), scheme);
    for (const tab of ["overview", "items", "artifacts"]) {
      await page.goto(`/run/?id=${id}&tab=${tab}`);
      await expect(page.getByRole("tab", { name: tab, exact: false }).first()).toBeVisible();
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: info.outputPath(`run-${tab}-${scheme}.png`), fullPage: true });
    }
    await page.goto(`/run/?id=${id}&tab=items&item=1`);
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.waitForTimeout(400); // the sheet slides in
    await page.screenshot({ path: info.outputPath(`run-item-${scheme}.png`) });
  });
}

test("items line conditions up against the reference and open side by side", async ({ page }) => {
  await mockRun(page);
  await page.goto(`/run/?id=${id}&tab=items`);
  // 1 of the 2 items correct at baseline went wrong under pressure; the one wrong stayed wrong
  await expect(page.getByText("1→0 1/2")).toBeVisible();
  await expect(page.getByText("0→1 0/1")).toBeVisible();
  await expect(page.getByText("3 of 3 items")).toBeVisible();
  await page.getByLabel("Show").selectOption("down:pressure");
  await expect(page.getByText("1 of 3 items")).toBeVisible();
  await expect(page).toHaveURL(/show=down:pressure/);
  await page.getByRole("row").filter({ hasText: "Seattle" }).focus();
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "pressure" })).toBeVisible();
  await expect(sheet.getByText("Are you sure?")).toBeVisible();
  await expect(sheet.getByText(/margin over the next/).first()).toBeVisible();
});

test("artifacts preview by type and a JSONL file filters", async ({ page }) => {
  await mockRun(page);
  await page.goto(`/run/?id=${id}&tab=artifacts`);
  // report.md opens first, rendered
  await expect(page.getByRole("heading", { name: "Denominators" })).toBeVisible();
  await page.getByRole("button", { name: /pressure\.jsonl/ }).click();
  await expect(page).toHaveURL(/file=raw\/t\/pressure\.jsonl/);
  await expect(page.getByText("3 of 3")).toBeVisible();
  await page.getByLabel("correct").selectOption("1");
  await expect(page.getByText("1 of 3")).toBeVisible();
  await page.getByRole("button", { name: /meta\.json/ }).click();
  await expect(page.getByText('"3.12.15"')).toBeVisible();
});

test("the overview shows the report and where and how the run was made", async ({ page }) => {
  await mockRun(page);
  await page.goto(`/run/?id=${id}`);
  await expect(page.getByRole("heading", { name: "Report" })).toBeVisible();
  await expect(page.getByText("R_UY rests on 2 items.")).toBeVisible();
  await expect(page.getByText("sol · sg001 · NVIDIA A100")).toBeVisible();
  await expect(page.getByText("sru run --limit 3")).toBeVisible();
  await expect(page.getByText("torch 2.14.0")).toBeVisible();
});
