import { expect, test } from "./fixtures";

const PAGES = [
  ["/", "Home"],
  ["/behavior/experiments/", "Experiments"],
  ["/launch/", "Launch"],
  ["/runs/", "Runs"],
  ["/compare/", "Compare"],
  ["/behavior/vectors/", "Vectors"],
  ["/behavior/training-sets/", "Training sets"],
  ["/behavior/circuits/", "Circuits"],
  ["/behavior/probe/", "Probe"],
  ["/behavior/", "Behavior"],
  ["/efficiency/", "Efficiency"],
  ["/efficiency/benchmark/", "Benchmark"],
  ["/efficiency/training/", "Training"],
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
  await expect(page).toHaveURL(/\/behavior\/vectors\/$/);
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
  await page.goto("/behavior/circuits/");
  await expect(page.getByRole("link", { name: "Launch a circuit" })).toHaveAttribute(
    "href",
    "/launch/?id=circuit",
  );
  // An experiment is a folder: the app reads it and shows the command that makes one.
  await page.goto("/behavior/experiments/");
  await expect(page.getByText("louped new my-question --domain honesty")).toBeVisible();
});

test("each domain has its own sidebar, entered from the top bar", async ({ page, isMobile }) => {
  // On a phone the sections and the pages share one sheet.
  const open = async () => {
    if (isMobile) await page.getByRole("button", { name: "Menu" }).click();
  };
  const sections = () =>
    isMobile ? page.getByRole("dialog") : page.getByRole("navigation", { name: "Sections" });
  const pages = () => page.getByRole("navigation", { name: "Pages" }).last();
  await page.goto("/");
  await open();
  await sections().getByRole("link", { name: "Behavior" }).click();
  await expect(page).toHaveURL(/\/behavior\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Behavior" })).toBeVisible();
  await open();
  await expect(pages().getByRole("link", { name: "Runs" })).toHaveCount(0);
  await pages().getByRole("link", { name: "Vectors" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Vectors" })).toBeVisible();
  await open();
  await expect(pages().getByRole("link", { name: "Vectors" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await sections().getByRole("link", { name: "Efficiency" }).click();
  await open();
  await expect(pages().getByRole("link", { name: "Benchmark" })).toBeVisible();
  await expect(pages().getByRole("link", { name: "Vectors" })).toHaveCount(0);
});

test("the sidebar folds to icons and stays folded", async ({ page, isMobile }) => {
  test.skip(isMobile, "the sidebar is a sheet on a phone");
  await page.goto("/behavior/vectors/");
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
  await page.goto("/behavior/vectors/");
  await page.getByRole("button", { name: "What is Layer?" }).click();
  await expect(page.getByRole("tooltip")).toContainText("Steering adds it back");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("link", { name: "Steer with refusal" })).toHaveAttribute(
    "href",
    "/behavior/probe/?vector=refusal&layer=3&tab=reply",
  );
});
