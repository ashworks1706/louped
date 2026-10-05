import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// A mocked API: one launchable script, a launch that queues a job, and job and run lists the test
// moves from live to an end state, as the server's worker and a script would.
const launchables = [
  {
    id: "script:hello/run.py",
    group: "Experiments",
    title: "hello/run.py",
    description: "Say hello.",
    config: null,
    recipe: null,
  },
];

const health = { status: "ok", version: "0.0.0", home: "/tmp", launching: true };

const run = (status: string) => ({
  id: "m-1",
  kind: "training",
  name: "sft",
  experiment: "refusal-finetuning",
  status,
  created: "2026-10-01T00:00:00Z",
  model: "tiny",
  metrics: {},
  samples: null,
});

async function mockApi(
  page: Page,
  {
    launch = { status: 200 } as { status: number; detail?: string },
    jobs = [] as Record<string, unknown>[],
    runs = [] as Record<string, unknown>[],
  } = {},
) {
  await page.route("**/api/health", (r) => r.fulfill({ json: health }));
  await page.route("**/api/launch", async (r) => {
    if (r.request().method() !== "POST") return r.fulfill({ json: launchables });
    if (launch.status !== 200)
      return r.fulfill({ status: launch.status, json: { detail: launch.detail } });
    const job = {
      id: "j1",
      title: "hello/run.py",
      argv: ["python", "hello/run.py"],
      status: "running",
      created: "2026-10-01T00:00:00Z",
      started: "2026-10-01T00:00:00Z",
    };
    jobs.push(job);
    return r.fulfill({ json: job });
  });
  await page.route("**/api/launch/options?*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: jobs }));
  await page.route("**/api/launch/jobs/j1", (r) => r.fulfill({ json: { ...jobs[0], log: "" } }));
  await page.route("**/api/runs", (r) => r.fulfill({ json: runs }));
  return { jobs, runs };
}

/** Lets a toast finish its entry animation before a screenshot. */
const settle = (page: Page) => page.waitForTimeout(500);

for (const [end, title, detail] of [
  ["succeeded", "Job finished", "exit 0 in 2m 5s"],
  ["failed", "Job failed", "exit 1 in 2m 5s"],
] as const) {
  test(`a job that ${end} is announced on any page`, async ({ page }, info) => {
    const { jobs } = await mockApi(page);
    await page.goto("/launch/");
    await page.getByRole("button", { name: "Launch" }).click();
    await expect(page.getByText("hello/run.py launched")).toBeVisible();
    await expect(page).toHaveURL(/\/job\/\?id=j1/);

    // Leave the job page: the notice must not depend on watching the job.
    await page.getByRole("link", { name: "Runs", exact: true }).first().click();
    Object.assign(jobs[0], {
      status: end,
      ended: "2026-10-01T00:02:05Z",
      exit_code: end === "succeeded" ? 0 : 1,
    });
    await expect(page.getByText(title)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(detail)).toBeVisible();
    await settle(page);
    await page.screenshot({ path: info.outputPath(`job-${end}.png`) });
  });
}

test("a job lost to a server restart says so, not exit unknown", async ({ page }) => {
  const { jobs } = await mockApi(page, {
    jobs: [{ id: "j0", title: "hello/run.py", argv: [], status: "running", created: "x" }],
  });
  // The watcher asks for jobs once health says this server launches; change the job after that.
  const firstLook = page.waitForResponse("**/api/launch/jobs");
  await page.goto("/runs/");
  await firstLook;
  Object.assign(jobs[0], { status: "failed", exit_code: null });
  await expect(page.getByText("The server restarted before it ended.")).toBeVisible({
    timeout: 10_000,
  });
});

test("a run started outside the app is announced when it ends", async ({ page }, info) => {
  test.slow(); // a live run polls every 3s
  const { runs } = await mockApi(page, { runs: [run("running")] });
  await page.addInitScript(() => localStorage.setItem("theme", "light"));
  await page.goto("/runs/");
  await expect(page.getByRole("cell", { name: /refusal-finetuning/ })).toBeVisible();
  runs[0] = run("finished");
  await expect(page.getByText("Training finished")).toBeVisible({ timeout: 10_000 });
  await settle(page);
  await page.screenshot({ path: info.outputPath("run-finished-light.png") });
});

test("what had already ended when the page opened is not announced", async ({ page }) => {
  await mockApi(page, {
    jobs: [
      {
        id: "j0",
        title: "old.py",
        argv: [],
        status: "succeeded",
        created: "2026-09-30T00:00:00Z",
        exit_code: 0,
      },
    ],
    runs: [run("finished")],
  });
  await page.goto("/runs/");
  await expect(page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
  await page.waitForTimeout(4000); // past one live poll
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0);
});

test("a failed action shows the server's message in a toast", async ({ page }, info) => {
  await mockApi(page, { launch: { status: 409, detail: "a job is already running" } });
  await page.goto("/launch/");
  await page.getByRole("button", { name: "Launch" }).click();
  await expect(page.getByText("Launch failed")).toBeVisible();
  await expect(page.getByText("a job is already running")).toBeVisible();
  await settle(page);
  await page.screenshot({ path: info.outputPath("launch-error.png") });
});
