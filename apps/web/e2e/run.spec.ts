import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// An analysis run that wrote one JSONL file per condition, a report and its RunMeta: what a paper
// harness leaves behind.
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
  // one file, one row per question and arm, as an engine's own benchmark writes it
  "bench/records.jsonl": jsonl([
    { q: "a", arm: "closed-book", em: 0, ttft_ms: 40 },
    { q: "b", arm: "closed-book", em: 1, ttft_ms: 41 },
    { q: "a", arm: "retrieval", em: 1, ttft_ms: 95 },
    { q: "b", arm: "retrieval", em: 1, ttft_ms: 97 },
  ]),
  // an agent's trace: one request's events, each with a time and a kind
  "traces/r1.jsonl": jsonl([
    {
      request_id: "r1",
      at: "2026-09-13T00:23:08.000Z",
      kind: "request_started",
      input: "is noble open",
    },
    {
      request_id: "r1",
      at: "2026-09-13T00:23:08.100Z",
      kind: "retrieval",
      duration_ms: 99,
      query: "noble hours",
    },
    { request_id: "r1", at: "2026-09-13T00:23:10.700Z", kind: "completed", status: "answered" },
  ]),
  "traces/r2.jsonl": jsonl([
    { request_id: "r2", at: "2026-09-13T01:00:00.000Z", kind: "request_started", input: "parking" },
    { request_id: "r2", at: "2026-09-13T01:00:01.500Z", kind: "completed", status: "answered" },
  ]),
  "raw/t/pressure.jsonl": jsonl([
    { qid: 1, condition: "pressure", correct: 0, scores: [-2, -1], second_turn: "Are you sure?" },
    { qid: 2, condition: "pressure", correct: 1, scores: [-1, -3], second_turn: "Are you sure?" },
    { qid: 3, condition: "pressure", correct: 0, scores: [-2, -1], second_turn: "Are you sure?" },
  ]),
};

/** The run's script at its commit on the forge, as the server gives it. */
const CODE = "https://github.com/o/r/blob/a1b2c3d4e5f60718/experiments/pushback-baseline/run.py";

async function mockRun(page: Page, history: Record<string, object[]> = {}) {
  await page.route(`**/api/runs/${id}`, (r) =>
    r.fulfill({
      json: {
        id,
        kind: "analysis",
        name: "baseline · llama_test_n3",
        experiment: "pushback-baseline",
        status: "finished",
        created: "2026-10-04T08:00:00Z",
        model: "llama",
        metrics: { "t/r_uy": 50 },
        samples: null,
        host: "sol",
        params: {},
        tags: { "louped.host": "sol", "louped.node": "sg001", "louped.gpu": "NVIDIA A100" },
        history,
        artifacts: Object.entries(files).map(([path, text]) => ({ path, size: text.length })),
        scorers: [],
        error: null,
        code: {
          commit: "a1b2c3d4e5f60718",
          dirty: true,
          path: "experiments/pushback-baseline/run.py",
          url: CODE,
          pushed: false,
        },
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

test("one file of records lines up by a column such as an arm", async ({ page }) => {
  await mockRun(page);
  await page.goto(`/run/?id=${id}&tab=artifacts&file=bench/records.jsonl`);
  await expect(page.getByText("4 of 4")).toBeVisible();
  await page.getByLabel("Line up by").selectOption("arm");
  await expect(page).toHaveURL(/by=arm/);
  await expect(page.getByText("2 of 2 items")).toBeVisible();
  // closed-book is the reference (first seen); retrieval fixed one of the one it got wrong
  await expect(page.getByText("0→1 1/1")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "retrieval" })).toBeVisible();
});

test("the machine's samples show under Hardware, not among the results", async ({ page }) => {
  // 100 W for 10 s is 1000 J; memory peaks at 2048 MB
  const at = (s: number) => 1_760_000_000_000 + s * 1000;
  const series = (values: number[]) =>
    values.map((value, i) => ({ step: i, value, timestamp: at(i * 5) }));
  await mockRun(page, {
    "system/gpu_0_power_usage_watts": series([100, 100, 100]),
    "system/gpu_0_utilization_percentage": series([10, 90, 50]),
    "system/gpu_0_memory_usage_megabytes": series([1024, 2048, 1536]),
    "system/cpu_utilization_percentage": series([5, 7, 6]),
  });
  await page.goto(`/run/?id=${id}`);
  const hardware = page.locator("section").filter({ hasText: "Hardware" });
  await expect(hardware.getByText("1000 J")).toBeVisible();
  await expect(hardware.getByText("2.0 GB")).toBeVisible();
  await expect(hardware.getByText("GPU 0 utilisation")).toBeVisible();
  // the results grid keeps only the run's own numbers
  await expect(page.getByText("system/cpu_utilization_percentage")).toHaveCount(0);
});

test("an agent's trace reads as a timeline, one file or the whole folder", async ({ page }) => {
  await mockRun(page);
  await page.goto(`/run/?id=${id}&tab=artifacts&file=traces/r1.jsonl`);
  await expect(page.getByText("1 trace · 3 events · 3 kinds")).toBeVisible();
  await expect(page.getByText("+2.70 s")).toBeVisible();
  await page.getByRole("button", { name: /retrieval/ }).click();
  await expect(page.getByText("noble hours").last()).toBeVisible();
  await page.getByRole("button", { name: "every file in traces/, as one (2)" }).click();
  await expect(page.getByText("2 traces · 5 events · 3 kinds")).toBeVisible();
  await page.getByRole("button", { name: "table", exact: true }).click();
  await expect(page).toHaveURL(/view=table/);
  await expect(page.getByText("5 of 5")).toBeVisible();
});

test("the overview shows the report and where and how the run was made", async ({ page }) => {
  await mockRun(page);
  await page.goto(`/run/?id=${id}`);
  await expect(page.getByRole("heading", { name: "Report" })).toBeVisible();
  await expect(page.getByText("R_UY rests on 2 items.")).toBeVisible();
  await expect(page.getByText("sol · sg001 · NVIDIA A100")).toBeVisible();
  await expect(page.getByText("sru run --limit 3")).toBeVisible();
  await expect(page.getByText("torch 2.14.0")).toBeVisible();
  const code = page.locator('[data-part="run.overview/provenance/code"]');
  await expect(code.getByRole("link", { name: "Code" })).toHaveAttribute("href", CODE);
  await expect(code).toContainText("a1b2c3d4e5f6");
  await expect(code).toContainText("uncommitted changes");
  await expect(code).toContainText("not pushed");
});
