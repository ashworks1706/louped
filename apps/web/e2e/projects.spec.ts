import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { experiment, mock } from "./items-run";
import { detail, mockProjects, orphan } from "./projects-api";

async function mockAll(page: Page) {
  await mock(page);
  await mockProjects(page);
}

/** Answers a write with body, keeping what was sent; reads fall through to the earlier mocks. */
async function capture(page: Page, glob: string, method: string, body: unknown) {
  const sent: unknown[] = [];
  await page.route(glob, (r) => {
    if (r.request().method() !== method) return r.fallback();
    sent.push(r.request().postDataJSON());
    return r.fulfill({ json: body });
  });
  return sent;
}

for (const scheme of ["dark", "light"] as const) {
  test(`projects show as cards and open on their page (${scheme})`, async ({ page }, info) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockAll(page);
    await page.goto("/projects/");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    const card = page.locator('[data-part="projects/card/pushback"]');
    await expect(card).toContainText("Sycophancy under pushback");
    await expect(card).toContainText("When and why models cave");
    await expect(card).toContainText("1 experiment");
    await expect(card).toContainText("multi-turn");
    // a name only experiments give is listed, said to have no README
    await expect(page.locator('[data-part="projects/card/gone"]')).toContainText("no README");
    await page.screenshot({ path: info.outputPath(`projects-${scheme}.png`), fullPage: true });

    await card.click();
    await expect(page).toHaveURL(/\/projects\/p\/\?name=pushback/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sycophancy under pushback");
    await expect(page.locator('[data-part="projects/link/paper"] a')).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/2310.13548",
    );
    await expect(page.locator('[data-part="projects/meta/models"]')).toContainText(
      "Qwen/Qwen2.5-0.5B-Instruct",
    );
    await expect(page.locator('[data-part="projects/meta/datasets"]')).toContainText("none");
    await expect(page.getByText("Find when a model caves.")).toBeVisible();
    await expect(page.locator('[data-part="experiments/row/hello"]')).toBeVisible();
    await expect(page.locator('[data-part="runs/row/m-1"]')).toBeVisible();
    await page.screenshot({ path: info.outputPath(`project-${scheme}.png`), fullPage: true });

    // the README section's ? says what it is
    await page
      .locator('[data-part="projects/section/readme"]')
      .getByRole("button", { name: "What is this?" })
      .click();
    await expect(page.getByRole("tooltip")).toContainText("projects/pushback/README.md");
  });
}

test("an experiment links its project, and the lists badge and filter by it", async ({ page }) => {
  await mockAll(page);
  await page.route("**/api/experiments", (r) =>
    r.fulfill({ json: [{ ...experiment, project: "pushback" }, orphan] }),
  );
  await page.goto("/behavior/experiment/?name=hello");
  const link = page.locator('[data-part="experiment/meta/project"] a');
  await expect(link).toHaveText("pushback");
  await link.click();
  await expect(page).toHaveURL(/\/projects\/p\/\?name=pushback/);

  await page.goto("/behavior/experiments/");
  await expect(page.locator('[data-part="experiments/row/hello"]')).toContainText("pushback");
  await page.getByLabel("Project").selectOption("gone");
  await expect(page).toHaveURL(/project=gone/);
  await expect(page.locator('[data-part="experiments/row/second-turn"]')).toBeVisible();
  await expect(page.locator('[data-part="experiments/row/hello"]')).toHaveCount(0);
});

test("New project writes its README and opens it", async ({ page }, info) => {
  await mockAll(page);
  const sent = await capture(page, "**/api/projects", "POST", detail);
  await page.goto("/projects/");
  await page.locator('[data-part="projects/new"]').click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("pushback");
  await dialog.getByLabel("Title").fill("Sycophancy under pushback");
  await dialog.getByLabel("Summary, one line").fill("When models cave.");
  await dialog.getByLabel("Status").selectOption("parked");
  await page.screenshot({ path: info.outputPath("new-project.png") });
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/projects\/p\/\?name=pushback/);
  expect(sent).toEqual([
    {
      name: "pushback",
      title: "Sycophancy under pushback",
      summary: "When models cave.",
      status: "parked",
    },
  ]);
});

test("New experiment starts one inside the project", async ({ page }) => {
  await mockAll(page);
  const sent = await capture(page, "**/api/experiments", "POST", {
    ...experiment,
    name: "flip",
    project: "pushback",
  });
  await page.goto("/projects/p/?name=pushback");
  await page.locator('[data-part="projects/new-experiment"] button').click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Domain")).toHaveValue("honesty");
  await dialog.getByLabel("Name, for the question").fill("flip");
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/behavior\/experiment\/\?name=flip/);
  expect(sent).toEqual([{ name: "flip", domain: "honesty", project: "pushback" }]);
});

test("Edit metadata replaces the front matter", async ({ page }, info) => {
  await mockAll(page);
  const saved = { ...detail, status: "done", datasets: ["truthful_qa"] };
  const sent = await capture(page, "**/api/projects/pushback/meta", "PUT", saved);
  await page.goto("/projects/p/?name=pushback");
  await page.locator('[data-part="projects/edit"] button').click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Links, one a line: name URL")).toHaveValue(
    "repo https://github.com/me/pushback\npaper https://arxiv.org/abs/2310.13548",
  );
  await dialog.getByLabel("Status").selectOption("done");
  await dialog.getByLabel("Datasets").fill("truthful_qa");
  await page.screenshot({ path: info.outputPath("edit-project.png") });
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('[data-part="projects/meta/datasets"]')).toContainText("truthful_qa");
  expect(sent).toEqual([
    {
      title: detail.title,
      status: "done",
      summary: detail.summary,
      tags: detail.tags,
      links: detail.links,
      models: detail.models,
      datasets: ["truthful_qa"],
      benchmarks: detail.benchmarks,
    },
  ]);
});

test("a project experiments name with no README says so and makes it", async ({ page }) => {
  await mockAll(page);
  const sent = await capture(page, "**/api/projects", "POST", { ...detail, name: "gone" });
  await page.goto("/projects/p/?name=gone");
  const note = page.locator('[data-part="projects/missing"]');
  await expect(note).toContainText("projects/gone/README.md does not exist");
  await expect(note).toContainText("1 experiment names it");
  await expect(page.locator('[data-part="experiments/row/second-turn"]')).toBeVisible();
  await expect(page.locator('[data-part="projects/edit"]')).toHaveCount(0);
  await page.locator('[data-part="projects/create"]').click();
  await expect.poll(() => sent).toEqual([{ name: "gone", title: "gone" }]);
});

test("with no projects, the page says what one is and offers New project", async ({ page }) => {
  await mockAll(page);
  await page.route("**/api/projects", (r) => r.fulfill({ json: [] }));
  await page.goto("/projects/");
  const empty = page.locator('[data-part="empty/no-projects-yet"]');
  await expect(empty).toContainText("projects/<name>/README.md");
  await expect(empty.getByRole("button", { name: "New project" })).toBeVisible();

  // a server that does not launch writes nothing: the command instead
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching: false } }),
  );
  await page.reload();
  await expect(empty).toContainText("louped project new my-project");
  await expect(page.getByRole("button", { name: "New project" })).toHaveCount(0);
});

test("G then J jumps to projects", async ({ page, isMobile }) => {
  test.skip(isMobile, "G jumps are a keyboard's");
  await mockAll(page);
  await page.goto("/");
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/\/projects\/$/);
});
