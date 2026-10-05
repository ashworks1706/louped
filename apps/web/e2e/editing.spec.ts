import { expect, test } from "@playwright/test";

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
  artifacts: [{ path: "report.md", size: 30 }],
  scorers: [],
  error: null,
  log: null,
};

for (const launching of [true, false]) {
  test(`a run's report ${launching ? "is edited beside its rendering" : "is read only when shared"}`, async ({
    page,
  }, info) => {
    let report = "# Does it flip?\n\nVerdict: \n";
    const saved: string[] = [];
    await page.route("**/api/health", (r) =>
      r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching, remote: null } }),
    );
    await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: run }));
    await page.route("**/api/runs/m-1/artifacts/report.md", (r) => {
      if (r.request().method() === "PUT") {
        report = (r.request().postDataJSON() as { text: string }).text;
        saved.push(report);
        return r.fulfill({ json: { text: report } });
      }
      return r.fulfill({ body: report });
    });
    await page.goto("/run/?id=m-1");
    await expect(page.getByRole("article").getByText("Verdict:")).toBeVisible();
    const edit = page.getByRole("button", { name: "Edit report.md" });
    if (!launching) {
      await expect(edit).toHaveCount(0);
      return;
    }
    await edit.click();
    const box = page.getByRole("textbox", { name: "report.md" });
    await box.fill("# Does it flip?\n\nVerdict: **right**\n");
    await expect(page.getByLabel("Preview").locator("strong")).toHaveText("right");
    await page.screenshot({ path: info.outputPath("editing.png"), fullPage: true });
    await box.press("ControlOrMeta+s");
    await expect(box).toHaveCount(0);
    expect(saved).toEqual(["# Does it flip?\n\nVerdict: **right**\n"]);
    await expect(page.locator("article strong")).toHaveText("right");
  });
}
