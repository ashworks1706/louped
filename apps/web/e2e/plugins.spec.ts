import { DEFAULT_LAYOUT, expect, test } from "./fixtures";

const plugins = [
  {
    name: "verdicts",
    title: "Verdicts",
    section: "behavior",
    description: "Judge each example.",
    panel: true,
    error: null,
  },
  {
    name: "broken",
    title: "Broken",
    section: "workspace",
    description: "",
    panel: false,
    error: "RuntimeError: typo",
  },
];

for (const scheme of ["dark", "light"] as const) {
  test(`a plugin's page is in its section's sidebar and themed like the app in ${scheme}`, async ({
    page,
  }, info) => {
    await page.addInitScript((t) => localStorage.setItem("theme", t), scheme);
    await page.route("**/api/plugins", (r) => r.fulfill({ json: plugins }));
    await page.route("**/x/verdicts/", (r) =>
      r.fulfill({
        contentType: "text/html",
        body: '<body style="background:var(--background);color:var(--foreground);font-family:var(--font-geist-sans)"><p>3 verdicts left</p></body>',
      }),
    );
    await page.goto("/behavior/x/?name=verdicts");
    if (info.project.name === "desktop")
      await expect(page.getByRole("link", { name: "Verdicts" })).toHaveAttribute(
        "aria-current",
        "page",
      );
    await expect(page.getByRole("heading", { level: 1, name: "Verdicts" })).toBeVisible();
    const panel = page.frameLocator('iframe[title="verdicts"]');
    await expect(panel.getByText("3 verdicts left")).toBeVisible();
    const colour = await page
      .locator('iframe[title="verdicts"]')
      .evaluate((f: HTMLIFrameElement) =>
        f.contentDocument!.documentElement.style.getPropertyValue("--foreground"),
      );
    expect(colour.trim()).not.toBe("");
    await page.screenshot({ path: info.outputPath(`plugin-${scheme}.png`), fullPage: true });
  });
}

test("a plugin that did not load shows why on its page", async ({ page }) => {
  await page.route("**/api/plugins", (r) => r.fulfill({ json: plugins }));
  await page.goto("/x/?name=broken");
  await expect(page.getByText("RuntimeError: typo")).toBeVisible();
});

// a plugin page that shows the query it was opened with
const echo = (r: import("@playwright/test").Route) =>
  r.fulfill({
    contentType: "text/html",
    body: "<body><p id=q></p><script>q.textContent = location.search</script></body>",
  });
const tabs = [{ ...plugins[0], panel: false, run: true, experiment: true }];
// the server's default gives every plugin with a run.html or experiment.html a tab
const withTabs = {
  ...DEFAULT_LAYOUT,
  regions: {
    ...DEFAULT_LAYOUT.regions,
    "run.tabs": [...DEFAULT_LAYOUT.regions["run.tabs"], { block: "plugin", plugin: "verdicts" }],
    "experiment.tabs": [
      ...DEFAULT_LAYOUT.regions["experiment.tabs"],
      { block: "plugin", plugin: "verdicts" },
    ],
  },
};

test("a plugin adds a tab to a run's page, opened with the run's id", async ({ page }, info) => {
  await page.route("**/api/plugins", (r) => r.fulfill({ json: tabs }));
  await page.route("**/api/ui/layout*", (r) => r.fulfill({ json: withTabs }));
  await page.route("**/x/verdicts/run.html*", echo);
  await page.route("**/api/runs/m-1", (r) =>
    r.fulfill({
      json: {
        id: "m-1",
        kind: "analysis",
        name: "a run",
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
      },
    }),
  );
  await page.goto("/run/?id=m-1");
  await page.getByRole("tab", { name: "Verdicts" }).click();
  await expect(page.frameLocator('iframe[title="verdicts"]').getByText("?run=m-1")).toBeVisible();
  await page.screenshot({ path: info.outputPath("plugin-run-tab.png"), fullPage: true });
});

test("a plugin adds a tab to an experiment's page, opened with its name", async ({ page }) => {
  await page.route("**/api/plugins", (r) => r.fulfill({ json: tabs }));
  await page.route("**/api/ui/layout*", (r) => r.fulfill({ json: withTabs }));
  await page.route("**/x/verdicts/experiment.html*", echo);
  await page.route("**/api/runs", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/launch", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/experiments/hello", (r) =>
    r.fulfill({
      json: {
        name: "hello",
        axis: "behavior",
        domain: "honesty",
        domain_title: "Honesty",
        status: "active",
        question: "Q?",
        result: null,
        runs: [],
        readme: "# hello\n",
      },
    }),
  );
  await page.goto("/behavior/experiment/?name=hello&tab=x-verdicts");
  await expect(
    page.frameLocator('iframe[title="verdicts"]').getByText("?experiment=hello"),
  ).toBeVisible();
});
