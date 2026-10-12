import { expect, test } from "./fixtures";

const PAGES = [
  ["/", "Overview"],
  ["/experiments/", "Experiments"],
  ["/launch/", "Launch"],
  ["/runs/", "Runs"],
  ["/compare/", "Compare"],
  ["/hub/", "Hub"],
  ["/vectors/", "Vectors"],
  ["/training-sets/", "Training sets"],
  ["/circuits/", "Circuits"],
  ["/probe/", "Probe"],
  ["/speed/", "Speed"],
  ["/datasets/", "Datasets"],
  ["/benchmarks/", "Benchmarks"],
  ["/reports/", "Reports"],
  ["/sources/", "Sources"],
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
  // An experiment is a folder: the app reads it and shows the command that makes one.
  await page.goto("/experiments/");
  await expect(page.getByText("louped new my-question --domain honesty")).toBeVisible();
});

test("one sidebar lists every page once, and old addresses move", async ({ page, isMobile }) => {
  const open = async () => {
    if (isMobile) await page.getByRole("button", { name: "Menu" }).click();
  };
  const pages = () => page.getByRole("navigation", { name: "Pages" }).last();
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Sections" })).toHaveCount(0);
  await open();
  for (const name of ["Experiments", "Runs", "Probe", "Speed", "Datasets", "Benchmarks"])
    await expect(pages().getByRole("link", { name, exact: true })).toHaveCount(1);
  await pages().getByRole("link", { name: "Vectors" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Vectors" })).toBeVisible();
  await open();
  await expect(pages().getByRole("link", { name: "Vectors" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  // a bookmark from when each domain had its own pages opens the page where it is now
  await page.goto("/efficiency/benchmarks/?task=x");
  await expect(page).toHaveURL(/\/benchmarks\/\?axis=efficiency&task=x$/);
  await page.goto("/behavior/training/");
  await expect(page).toHaveURL(/\/runs\/\?kind=training$/);
});

test("the sidebar folds to icons and stays folded", async ({ page, isMobile }) => {
  test.skip(isMobile, "the sidebar is a sheet on a phone");
  await page.goto("/vectors/");
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  const pages = page.getByRole("navigation", { name: "Pages" });
  await expect(pages.getByRole("link", { name: "Vectors" })).toHaveText("");
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
});

test("a vector says what each column means and opens Probe with it", async ({ page }) => {
  await page.route("**/api/vectors", (r) =>
    r.fulfill({
      json: [
        {
          name: "refusal",
          model: "tiny",
          layer: 3,
          method: "diff-in-means",
          norm: 4.2,
          dim: 8,
          run: null,
          notes: null,
          created: "2026-09-27T00:00:00Z",
        },
      ],
    }),
  );
  await page.goto("/vectors/");
  await page.getByRole("button", { name: "What is Layer?" }).click();
  await expect(page.getByRole("tooltip")).toContainText("Steering adds it back");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("link", { name: "Steer with refusal" })).toHaveAttribute(
    "href",
    "/probe/?vector=refusal&layer=3&tab=reply",
  );
});
