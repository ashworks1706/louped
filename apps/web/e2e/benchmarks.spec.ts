import { benchmarks, spec } from "./datasets-api";
import { expect, test } from "./fixtures";
import { mockPages } from "./pages-api";

// The Benchmarks pages: eval tasks with their runs as leaderboards, a Hub dataset made a
// benchmark, and louped bench runs by speed.
test("each eval task's runs are its leaderboard, launched from there", async ({ page }, info) => {
  await mockPages(page);
  await page.goto("/behavior/benchmarks/");
  await expect(page.getByRole("heading", { level: 1, name: "Benchmarks" })).toBeVisible();
  const tasks = page.locator('[data-part^="benchmarks/task/"]');
  // tasks with runs and the project's; inspect_evals' without runs wait for a search
  await expect(tasks).toHaveCount(3);
  await expect(page.locator('[data-part="benchmarks/more"]')).toContainText("with no runs yet: 1");
  await page.getByLabel("Search eval tasks").fill("mmlu");
  await expect(tasks).toHaveCount(1);
  await expect(tasks.first()).toContainText("inspect_evals/mmlu_0_shot");
  await page.getByLabel("Search eval tasks").fill("");
  await page.screenshot({ path: info.outputPath("benchmarks.png"), fullPage: true });

  await page.locator('[data-part="benchmarks/task/louped%2Fgsm8k"]').click();
  await expect(page).toHaveURL(/task=louped(%2F|\/)gsm8k/);
  const entries = page.locator('[data-part^="benchmarks/entry/"]');
  await expect(entries).toHaveCount(2);
  await expect(entries.first()).toContainText("louped/Qwen/Qwen2.5-1.5B-Instruct");
  await expect(entries.first()).toContainText("0.620");
  await expect(page.locator('[data-part="benchmarks/board/spec"]')).toContainText(
    "question → answer",
  );
  await expect(entries.first().getByRole("link")).toHaveAttribute("href", "/run/?id=e-1");
  await page.waitForTimeout(300); // the panel slides in
  await page.screenshot({ path: info.outputPath("leaderboard.png") });
  const launch = page.locator('[data-part="benchmarks/board/launch"] a');
  await expect(launch).toHaveAttribute("href", "/launch/?id=eval&task=louped%2Fgsm8k");

  // Launch opens with the task filled in
  await page.route("**/api/launch", (r) =>
    r.fulfill({
      json: [{ id: "eval", group: "Commands", title: "inspect eval", description: "Any task." }],
    }),
  );
  await page.route("**/api/launch/options?*", (r) =>
    r.fulfill({
      json: [{ flag: "task", kind: "text", default: null, help: "", choices: [], required: true,
               suggest: "evals" }], // prettier-ignore
    }),
  );
  await launch.click();
  await expect(page.locator("#opt-task")).toHaveValue("louped/gsm8k");
});

test("a Hub dataset becomes a benchmark from its field mapping", async ({ page }) => {
  await mockPages(page);
  const sent: unknown[] = [];
  await page.route("**/api/benchmarks", (r) => {
    if (r.request().method() !== "POST") return r.fulfill({ json: benchmarks });
    sent.push(r.request().postDataJSON());
    return r.fulfill({
      json: {
        benchmark: { ...benchmarks[0], runs: 0, best: null },
        checked: false,
        note: "not checked against the dataset: could not reach the dataset viewer",
      },
    });
  });
  await page.goto("/behavior/benchmarks/");
  await page.locator('[data-part="benchmarks/add"]').click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name", { exact: true }).fill("gsm8k");
  await dialog.getByLabel("Dataset", { exact: true }).fill("openai/gsm8k");
  await dialog.getByLabel("Config", { exact: true }).fill("main");
  await dialog.getByLabel("Input field", { exact: true }).fill("question");
  await dialog.getByLabel("Target field", { exact: true }).fill("answer");
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect.poll(() => sent).toEqual([{ name: "gsm8k", ...spec }]);
  await expect(page.getByText("not checked against the dataset")).toBeVisible(); // said, not hidden
  await expect(page).toHaveURL(/task=louped(%2F|\/)gsm8k/); // its leaderboard opens
});

test("speed benchmarks by model and setting, newest or each model's fastest", async ({
  page,
}, info) => {
  await mockPages(page);
  await page.goto("/efficiency/benchmarks/");
  const rows = page.locator('[data-part^="benchmarks/speed/"]');
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(1)).toContainText("990.1");
  await expect(rows.nth(1)).toContainText("fastest");
  await page.screenshot({ path: info.outputPath("speed-benchmarks.png"), fullPage: true });
  await page.locator('[data-part="benchmarks/show/best"]').click();
  await expect(page).toHaveURL(/show=best/);
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("int8");

  // the speed tool keeps its URL, now named Speed
  await page.goto("/efficiency/benchmark/");
  await expect(page.getByRole("heading", { level: 1, name: "Speed" })).toBeVisible();

  await page.route("**/api/benchmarks/speed", (r) => r.fulfill({ json: [] }));
  await page.goto("/efficiency/benchmarks/");
  await expect(page.getByRole("link", { name: "Launch louped bench" })).toHaveAttribute(
    "href",
    "/launch/?id=bench",
  );
});
