import { expect, test } from "@playwright/test";

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
