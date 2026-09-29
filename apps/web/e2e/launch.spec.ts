import { expect, test, type Page } from "@playwright/test";

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
    description: "loupe train sft",
    config: "name: hello\nbase_model: tiny\n",
    recipe: "sft",
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
    r.fulfill({ json: r.request().url().includes("train") ? [] : options }),
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
  expect(sent[0]).toEqual({
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
  expect(sent[0]).toMatchObject({
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
