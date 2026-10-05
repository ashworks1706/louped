import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// A mocked API: one experiment script with three options, one training config, and a job list
// that gains the launched job.
const launchables = [
  {
    id: "script:hello/run.py",
    group: "Experiments",
    title: "hello/run.py",
    description: "Say hello.",
    config: null,
    recipe: null,
  },
  {
    id: "train:hello/sft.yaml",
    group: "Training",
    title: "hello/sft.yaml",
    description: "louped train sft",
    config: "name: hello\nbase_model: tiny\n",
    recipe: "sft",
  },
  {
    id: "grid",
    group: "Commands",
    title: "louped grid",
    description: "Conditions by tasks by seeds.",
    config: "# louped grid\nmodel: tiny\n",
    recipe: null,
  },
];
const options = [
  { flag: "--name", kind: "text", default: "world", help: "Who to greet.", choices: [] },
  { flag: "--loud", kind: "bool", default: "False", help: "", choices: [] },
  { flag: "--times", kind: "list", default: "1", help: "", choices: [] },
];

async function mockApi(page: Page) {
  const jobs: object[] = [];
  const sent: object[] = [];
  await page.route("**/api/launch", async (r) => {
    if (r.request().method() === "POST") {
      sent.push(r.request().postDataJSON());
      const job = {
        id: "j1",
        title: "hello/run.py",
        argv: ["python", "hello/run.py", "--loud"],
        status: "running",
        created: new Date().toISOString(),
      };
      jobs.push(job);
      return r.fulfill({ json: job });
    }
    return r.fulfill({ json: launchables });
  });
  await page.route("**/api/launch/options?*", (r) =>
    r.fulfill({ json: /train|grid/.test(r.request().url()) ? [] : options }),
  );
  await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: jobs }));
  await page.route("**/api/launch/jobs/j1", (r) =>
    r.fulfill({ json: { ...jobs[0], log: '{"run": "m-abc123"}\n' } }),
  );
  return sent;
}

test("a script's options become a form, and launching sends only what changed", async ({
  page,
}) => {
  const sent = await mockApi(page);
  await page.goto("/launch/");
  await expect(page.getByText("Say hello.")).toBeVisible();
  await expect(page.getByLabel("--name")).toHaveValue("world");
  await page.getByLabel("--loud").check();
  await page.getByLabel("--times").fill("2 3");
  await expect(page.getByText("python experiments/hello/run.py --loud --times 2 3")).toBeVisible();
  await page.getByRole("button", { name: "Launch" }).click();
  // The request lands a moment after the click; poll rather than read it once.
  await expect
    .poll(() => sent[0])
    .toEqual({
      id: "script:hello/run.py",
      options: { "--loud": true, "--times": ["2", "3"] },
    });
  await expect(page.getByRole("link", { name: "m-abc123" })).toHaveAttribute(
    "href",
    "/run/?id=m-abc123",
  );
  await page.screenshot({ path: test.info().outputPath("launch.png"), fullPage: true });
});

test("a training config is edited in place and sent with its recipe", async ({ page }) => {
  const sent = await mockApi(page);
  await page.goto("/launch/?id=train:hello/sft.yaml");
  const config = page.getByLabel("Config");
  await expect(config).toHaveValue(/base_model: tiny/);
  await config.fill("name: edited\nbase_model: tiny\n");
  await page.getByLabel("Recipe").selectOption("dpo");
  await page.getByRole("button", { name: "Launch" }).click();
  await expect
    .poll(() => sent[0])
    .toMatchObject({
      id: "train:hello/sft.yaml",
      recipe: "dpo",
      config: "name: edited\nbase_model: tiny\n",
    });
});

test("a server that only reads says launching is off", async ({ page }) => {
  await page.route("**/api/launch", (r) => r.fulfill({ status: 403, json: { detail: "off" } }));
  await page.goto("/launch/");
  await expect(page.getByText("Launching is off on this server")).toBeVisible();
});

test("a grid's config is edited in place and sent without a recipe", async ({ page }) => {
  const sent = await mockApi(page);
  await page.goto("/launch/?id=grid");
  await expect(page.getByLabel("Recipe")).toHaveCount(0);
  await expect(page.getByText("louped grid grid.yaml")).toBeVisible();
  await page.getByLabel("Config").fill("# louped grid\nmodel: edited\n");
  await page.getByRole("button", { name: "Launch" }).click();
  await expect
    .poll(() => sent[0])
    .toEqual({ id: "grid", options: {}, config: "# louped grid\nmodel: edited\n" });
});

test("a launch exports for Sol and its result imports back", async ({ page }, info) => {
  await mockApi(page);
  let exported: unknown;
  await page.route("**/api/launch/export", (r) => {
    exported = r.request().postDataJSON();
    return r.fulfill({
      body: Buffer.from([0x1f, 0x8b]),
      headers: {
        "content-type": "application/gzip",
        "content-disposition": 'attachment; filename="louped-j2.tar.gz"',
      },
    });
  });
  let imported = "";
  await page.route("**/api/launch/import", (r) => {
    imported = r.request().headers()["content-type"];
    return r.fulfill({
      json: { job: "j2", host: "sol", exit_code: 0, runs: ["m-1", "e-2"], skipped: [] },
    });
  });
  await page.goto("/launch/");
  await page.getByLabel("Run on").selectOption("sol");
  await page.getByLabel("GPU", { exact: true }).selectOption("a30");
  await page.getByLabel("Hours").fill("2");
  await page.screenshot({ path: info.outputPath("export.png"), fullPage: true });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  expect((await download).suggestedFilename()).toBe("louped-j2.tar.gz");
  expect(exported).toMatchObject({
    id: "script:hello/run.py",
    target: { provider: "sol", gpu: "a30", gpus: 1, hours: 2 },
  });
  // A result comes back on Runs, where every job is followed.
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", version: "0.0.0", home: "/tmp", launching: true } }),
  );
  await page.goto("/runs/");
  await page.getByLabel("Result archive").setInputFiles({
    name: "louped-result-j2.tar.gz",
    mimeType: "application/gzip",
    buffer: Buffer.from([0x1f, 0x8b]),
  });
  await expect(page.getByText("2 runs imported from sol")).toBeVisible();
  expect(imported).toBe("application/gzip");
});

test("inspect eval's task is picked from the project's tasks and inspect_evals'", async ({
  page,
}, info) => {
  const sent = await mockApi(page);
  await page.route("**/api/launch", async (r) => {
    if (r.request().method() === "POST") {
      sent.push(r.request().postDataJSON());
      return r.fulfill({ json: { id: "j1", title: "inspect eval", argv: [], status: "queued" } });
    }
    return r.fulfill({
      json: [{ id: "eval", group: "Commands", title: "inspect eval", description: "Any task." }],
    });
  });
  await page.route("**/api/launch/options?*", (r) =>
    r.fulfill({
      json: [
        {
          flag: "task",
          kind: "text",
          default: null,
          help: "",
          choices: [],
          required: true,
          suggest: "evals",
        },
      ],
    }),
  );
  await page.route("**/api/evals", (r) =>
    r.fulfill({
      json: [
        {
          task: "experiments/hello/task.py@pushback",
          title: "pushback",
          group: "hello",
          about: "Does pushback flip answers?",
          samples: null,
          source: "project",
        },
        {
          task: "inspect_evals/gsm8k",
          title: "GSM8K",
          group: "Mathematics",
          about: "Grade school math word problems.",
          samples: 1319,
          source: "inspect_evals",
        },
      ],
    }),
  );
  await page.goto("/launch/?id=eval");
  await page.locator('[data-part="launch/browse/task"]').click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("This project · hello")).toBeVisible();
  await dialog.getByPlaceholder(/Search tasks/).fill("word problems");
  await expect(
    dialog.locator('[data-part="launch/eval/experiments%2Fhello%2Ftask.py%40pushback"]'),
  ).toBeHidden();
  await page.screenshot({ path: info.outputPath("eval-picker.png") });
  await dialog.locator('[data-part="launch/eval/inspect_evals%2Fgsm8k"]').click();
  await expect(page.locator("#opt-task")).toHaveValue("inspect_evals/gsm8k");
});
