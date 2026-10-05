import { expect, test } from "./fixtures";

const run = {
  id: "m-1",
  kind: "analysis",
  name: "baseline",
  experiment: "hello",
  status: "finished",
  created: null,
  model: null,
  metrics: {},
  samples: null,
  params: {},
  tags: {},
  history: {},
  artifacts: [],
  scorers: [],
  error: null,
  log: null,
};

for (const launching of [true, false]) {
  test(`a run ${launching ? "is deleted after one confirm" : "cannot be deleted when shared"}`, async ({
    page,
  }, info) => {
    let deleted = false;
    await page.route("**/api/health", (r) =>
      r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching, remote: null } }),
    );
    await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/runs", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/runs/m-1", (r) => {
      if (r.request().method() === "DELETE") {
        deleted = true;
        return r.fulfill({ status: 200, body: "null", contentType: "application/json" });
      }
      return r.fulfill({ json: run });
    });
    await page.goto("/run/?id=m-1");
    await expect(page.getByRole("heading", { name: "baseline" })).toBeVisible();
    const button = page.getByRole("button", { name: "Delete run" });
    if (!launching) {
      await expect(button).toHaveCount(0);
      return;
    }
    await button.click();
    const dialog = page.getByRole("dialog", { name: "Delete run baseline?" });
    await expect(dialog).toContainText("MLflow keeps it");
    await page.screenshot({ path: info.outputPath("delete-run.png") });
    await dialog.getByRole("button", { name: "Delete" }).click();
    await expect(page).toHaveURL(/\/runs\/$/);
    expect(deleted).toBe(true);
    await expect(page.getByText("Deleted baseline")).toBeVisible();
  });
}

test("a running job cannot be deleted until it stops", async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({
      json: { status: "ok", version: "0", home: "/x", launching: true, remote: null },
    }),
  );
  await page.route("**/api/launch/jobs/j-1", (r) =>
    r.fulfill({
      json: {
        id: "j-1",
        title: "hello/run.py",
        argv: ["python", "run.py"],
        status: "running",
        created: "2026-10-05T00:00:00Z",
        started: "2026-10-05T00:00:00Z",
        ended: null,
        exit_code: null,
        log: "",
      },
    }),
  );
  await page.goto("/job/?id=j-1");
  await expect(page.getByRole("button", { name: "Delete job" })).toBeDisabled();
});
