import { expect, test } from "@playwright/test";

const PAGES = [
  ["/", "Home"],
  ["/experiments/", "Experiments"],
  ["/launch/", "Launch"],
  ["/runs/", "Runs"],
  ["/compare/", "Compare"],
  ["/vectors/", "Vectors"],
  ["/circuits/", "Circuits"],
  ["/playground/", "Playground"],
] as const;

for (const [path, title] of PAGES) {
  test(`${title} renders without errors`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      // The API is not running in this test; its offline state is expected, not an error.
      if (m.type() === "error" && !m.text().includes("Failed to load resource"))
        errors.push(m.text());
    });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.locator('[data-slot="skeleton"]')).toHaveCount(0); // settled: data, empty or offline
    await page.screenshot({ path: info.outputPath(`${title.toLowerCase()}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });
}

test("command menu navigates", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcut");
  await page.goto("/");
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByPlaceholder("Go to, or run a command…")).toBeVisible();
  await page.keyboard.type("vectors");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/vectors\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Vectors" })).toBeVisible();
});

test("G then R jumps to runs", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcut");
  await page.goto("/");
  await page.keyboard.press("g");
  await page.keyboard.press("r");
  await expect(page).toHaveURL(/\/runs\/$/);
});

test("an empty page links to what fills it in the app, not a terminal", async ({ page }) => {
  for (const path of ["runs", "vectors", "graphs", "experiments"])
    await page.route(`**/api/${path}`, (r) => r.fulfill({ json: [] }));
  await page.goto("/runs/");
  await expect(page.getByRole("link", { name: "Launch a run" })).toHaveAttribute(
    "href",
    "/launch/",
  );
  await page.goto("/circuits/");
  await expect(page.getByRole("link", { name: "Launch a circuit" })).toHaveAttribute(
    "href",
    "/launch/?id=circuit",
  );
  await page.goto("/experiments/");
  await expect(page.getByRole("link", { name: "New experiment" }).last()).toBeVisible();
  await expect(page.locator("code")).toHaveCount(0);
});
