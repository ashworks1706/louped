import type { Page } from "@playwright/test";

import { DEFAULT_LAYOUT, expect, test } from "./fixtures";
import { mock } from "./items-run";
import { mockPages } from "./pages-api";
import kinds from "./part-kinds.json" with { type: "json" };

// Every part of a page has an address: a person Shift+clicks parts to hand them to their agent,
// a layout changes them by address, and the agent points back at them.
const KIND_PATTERNS = kinds.map((k) => k.part.split("/"));
const BLOCKS = Object.fromEntries(
  Object.entries(DEFAULT_LAYOUT.regions).map(([region, blocks]) => [
    region,
    (blocks as { block: string }[]).map((b) => b.block),
  ]),
) as Record<string, string[]>;
/** Whether an address names a kind of part, or a block of a region. */
const known = (id: string) => {
  const segs = id.split("/");
  if (segs.length <= 3 && BLOCKS[segs[0]]?.includes(segs[1])) return true;
  return KIND_PATTERNS.some(
    (want) => want.length === segs.length && want.every((w, i) => w === "*" || w === segs[i]),
  );
};

/** What a person can see or use on the page that has no address: none should be left. */
async function unaddressed(page: Page) {
  return page.evaluate(() => {
    const things =
      "button, select, input, textarea, a[href], th, tr, dt, h1, h2, h3, figure, [role=tab]";
    return [...document.querySelectorAll<HTMLElement>(things)]
      .filter((el) => el.getClientRects().length > 0 && !el.closest("[data-part]"))
      .filter((el) => !el.matches("thead tr")) // its headings are the columns' parts
      .filter((el) => !el.closest("[data-part-tray], [data-sonner-toaster], next-route-announcer"))
      .map((el) => el.outerHTML.slice(0, 160));
  });
}
const addresses = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("[data-part]")].map((el) => el.dataset.part!),
  );

const PAGES: [string, string][] = [
  ["home", "/"],
  ["runs", "/runs/"],
  ["experiments", "/behavior/experiments/"],
  ["experiment", "/behavior/experiment/?name=hello"],
  ["overview", "/run/?id=m-1"],
  ["items", "/run/?id=m-1&tab=items"],
  ["item", "/run/?id=m-1&tab=items&item=28"],
  ["artifacts", "/run/?id=m-1&tab=artifacts&file=raw%2Fbaseline.jsonl"],
  ["config", "/run/?id=m-1&tab=config"],
  ["samples", "/run/?id=e-1&tab=samples"],
  ["sample", "/run/?id=e-1&tab=samples&sample=1"],
  ["figures", "/run/?id=m-1&tab=figures"],
  ["training run", "/run/?id=t-1"],
  ["behavior", "/behavior/"],
  ["efficiency", "/efficiency/"],
  ["efficiency experiments", "/efficiency/experiments/"],
  ["probe reply", "/behavior/probe/?tab=reply"],
  ["probe inspect", "/behavior/probe/?tab=inspect"],
  ["probe patch", "/behavior/probe/?tab=patch"],
  ["probe dose", "/behavior/probe/?tab=dose"],
  ["benchmark", "/efficiency/benchmark/"],
  ["vectors", "/behavior/vectors/"],
  ["circuits", "/behavior/circuits/"],
  ["feature", "/behavior/feature/?run=m-1&f=12"],
  ["training", "/efficiency/training/"],
  ["compare", "/compare/?a=e-1&b=e-1"],
  ["compare curves", "/compare/?a=t-1&b=t-2"],
  ["compare sample", "/compare/?a=e-1&b=e-1&changed=false&sample=1"],
  ["launch", "/launch/?id=script%3Ahello%2Frun.py"],
  ["job", "/job/?id=j1"],
];

for (const [name, url] of PAGES) {
  test(`every part of ${name} has an address the server knows`, async ({ page }) => {
    await mockPages(page);
    await page.goto(url);
    await expect(page.locator("main [data-part]").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await unaddressed(page)).toEqual([]);
    expect((await addresses(page)).filter((id) => !known(id))).toEqual([]);
  });
}

test("Shift+click picks parts for the agent, with what they stand for", async ({
  page,
  context,
}, info) => {
  test.skip(info.project.name === "mobile", "Shift is a keyboard's");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await mock(page);
  const sent: { parts: { id: string; data: unknown; run: string | null }[] }[] = [];
  await page.route("**/api/ui/selection", (r) => {
    sent.push(r.request().postDataJSON());
    return r.fulfill({ json: sent.at(-1) });
  });
  await page.goto("/run/?id=m-1&tab=items");
  const row = page.locator('[data-part="items/row/28"]');
  const stat = page.locator('[data-part="items/stat/pressure"]');
  // the innermost part under the pointer: the item's id cell is the row's own, a condition's
  // cell is a part of its own
  await row
    .locator("td")
    .first()
    .click({ modifiers: ["Shift"] });
  await stat.click({ modifiers: ["Shift"] });
  await expect(page).not.toHaveURL(/item=28/); // a pick opens nothing
  const tray = page.getByRole("region", { name: "Picked parts" });
  await expect(tray).toContainText("2 picked");
  await expect
    .poll(() => sent.at(-1)?.parts.map((p) => p.id))
    .toEqual(["items/row/28", "items/stat/pressure"]);
  const [picked, rate] = sent.at(-1)!.parts;
  expect(picked.run).toBe("m-1");
  expect(picked.data).toMatchObject({
    qid: "28",
    compared_on: "correct",
    records: { baseline: { pred: "True" }, pressure: { pred: "False" } },
  });
  expect(rate.data).toMatchObject({ condition: "pressure", k: 1, n: 2, down: "1/2" });
  await expect(row).toHaveCSS("outline-style", "solid");
  await page.screenshot({ path: info.outputPath("picked.png") });

  await tray.getByRole("button", { name: "Copy" }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("louped part items/row/28");
  expect(copied).toContain('"pressure":{');

  await row
    .locator("td")
    .first()
    .click({ modifiers: ["Shift"] }); // again: dropped
  await expect(tray).toContainText("1 picked");
  await page.keyboard.press("Escape");
  await expect(tray).toHaveCount(0);
  await expect.poll(() => sent.at(-1)?.parts).toEqual([]);
  await row.click(); // without Shift, a click acts
  await expect(page).toHaveURL(/item=28/);
  await page.locator('[data-part="item/title"]').click({ modifiers: ["Shift"] });
  // over the open panel (which hides the page from a screen reader) and usable
  const over = page.locator("[data-part-tray]");
  await expect(over).toContainText("1 picked");
  await over.locator("button", { hasText: "Copy" }).click();
  await expect(page).toHaveURL(/item=28/); // the panel stays
  await page.keyboard.press("Escape"); // closes the panel, keeps the pick
  await expect(page).not.toHaveURL(/item=28/);
  await expect(tray).toContainText("1 picked");
});

test("a layout hides, renames and hints parts of the tool pages too", async ({ page }) => {
  await mockPages(page, {
    "playground/tab/dose": { hidden: false, order: 0 },
    "playground/tab/patch": { hidden: true },
    "playground/field/strength": { hidden: false, label: "Push", note: "Try 2 first." },
    "playground/field/follow-up": { hidden: true },
    "launch/option/--loud": { hidden: true },
    "launch/option/--name": { hidden: false, label: "who", note: "Your **advisor**." },
    "domain/section/runs": { hidden: true },
    "compare/section/paired": { hidden: false, note: "Read the interval, not the mean." },
    "feature/figure/histogram": { hidden: true },
    "job/log": { hidden: false, note: "The error is at the end." },
    "empty/no-experiments-here-yet": { hidden: false, note: "Start one with the agent." },
  });
  await page.goto("/behavior/probe/");
  const tabs = page.locator('[data-part^="playground/tab/"]');
  await expect(tabs).toHaveText(["Dose", "Reply", "Inspect"]);
  await expect(page.getByRole("tab", { name: "Dose" })).toHaveAttribute("aria-selected", "true");
  const strength = page.locator('[data-part="playground/field/strength"]');
  await expect(strength).toContainText("Push");
  await expect(strength).toContainText("Try 2 first.");
  await page.goto("/behavior/probe/?tab=reply");
  await expect(page.getByLabel("Prompt")).toBeVisible();
  await expect(page.getByLabel("Follow-up")).toHaveCount(0);

  await page.goto("/launch/?id=script%3Ahello%2Frun.py");
  await expect(page.locator("#opt---name")).toBeVisible();
  await expect(page.locator('[data-part="launch/option/--loud"]')).toHaveCount(0);
  await expect(page.locator('[data-part="launch/option/--name"]')).toContainText("who");
  await expect(page.locator('[data-part="launch/option/--name"] strong')).toHaveText("advisor");

  await page.goto("/behavior/");
  await expect(page.locator('[data-part="domain/section/tools"]')).toBeVisible();
  await expect(page.locator('[data-part="domain/section/runs"]')).toHaveCount(0);
  await page.goto("/efficiency/");
  await expect(page.locator('[data-part="empty/no-experiments-here-yet"]')).toContainText(
    "Start one with the agent.",
  );
  await page.goto("/compare/?a=e-1&b=e-1");
  await expect(page.locator('[data-part="compare/section/paired"]')).toContainText(
    "Read the interval, not the mean.",
  );
  await page.goto("/behavior/feature/?run=m-1&f=12");
  await expect(page.locator('[data-part="feature/figure/promotes"]')).toBeVisible();
  await expect(page.locator('[data-part="feature/figure/histogram"]')).toHaveCount(0);
  await page.goto("/job/?id=j1");
  await expect(page.locator('[data-part="job/log"]')).toContainText("The error is at the end.");
});

test("a layout's parts rename, explain, order, hide and set defaults", async ({ page }, info) => {
  await mock(page, {
    "items/stat/pressure": { hidden: false, label: "pushback", note: "Read this one first." },
    "items/column/claim": { hidden: true },
    "items/show": { hidden: false, default: "changed" },
    "item/field/*/abstain": { hidden: true },
    "item/field/item/gold": { hidden: false, order: 0 },
    "run/meta/id": { hidden: true },
    "run.overview/metrics/flips": { hidden: false, label: "answers flipped", order: 0 },
    "run.overview/metrics/accuracy": { hidden: false, about: "Right answers in the baseline." },
    "run/back": { hidden: true },
    "runs/action/launch": { hidden: true },
    "home/more/runs": { hidden: true },
  });
  await page.goto("/run/?id=m-1");
  await expect(page.locator('[data-part="run/meta/id"]')).toBeHidden();
  await expect(page.locator('[data-part="run/back"]')).toBeHidden();
  const cards = page.locator('[data-part^="run.overview/metrics/"]');
  await expect(cards.first()).toContainText("answers flipped");
  const accuracy = page.locator('[data-part="run.overview/metrics/accuracy"]');
  await accuracy.getByRole("button").first().click();
  await expect(page.getByText("Right answers in the baseline.")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.goto("/runs/");
  await expect(page.locator('[data-part="runs/action/launch"]')).toBeHidden();
  await page.goto("/");
  await expect(page.locator('[data-part="home/more/runs"]')).toBeHidden();

  await page.goto("/run/?id=m-1&tab=items");
  await expect(page.locator('[data-part="items/stat/pressure"]')).toContainText("pushback");
  await expect(page.getByText("Read this one first.")).toBeVisible();
  await expect(page.locator('[data-part="items/column/claim"]')).toHaveCount(0);
  await expect(page.locator('[data-part="items/count"]')).toHaveText("1 of 2 items"); // changed
  await page.screenshot({ path: info.outputPath("parts-items.png"), fullPage: true });

  await page.locator('[data-part="items/row/28"]').click();
  const item = page.locator('[data-part="item/section/item"]');
  await expect(item.locator("dt").first()).toHaveText("gold");
  await expect(page.locator('[data-part$="/abstain"]')).toHaveCount(0);
});

test("the agent opens a page and points at a part with a note", async ({ page }, info) => {
  await mock(page);
  let shown = false;
  const seen: unknown[] = [];
  await page.route("**/api/ui/show*", (r) => {
    const cue = {
      id: 1,
      at: Date.now() / 1000,
      url: "/run/?id=m-1&tab=items",
      parts: ["items/row/28", "items/row/404"],
      text: "Pressure flipped **this one**.",
      style: "spotlight",
      status: "pending",
      missing: [],
    };
    const fresh = !shown;
    shown = true;
    return r.fulfill({ json: { now: Date.now() / 1000, cues: fresh ? [cue] : [] } });
  });
  await page.route("**/api/ui/show/1/seen", (r) => {
    seen.push(r.request().postDataJSON());
    return r.fulfill({ json: {} });
  });
  await page.goto("/");
  await expect(page).toHaveURL(/tab=items/);
  const note = page.getByRole("status").filter({ hasText: "Pressure flipped" });
  await expect(note.locator("strong")).toHaveText("this one");
  await expect(page.locator("[data-cue-box]")).toHaveCount(1);
  await expect.poll(() => seen).toEqual([{ missing: ["items/row/404"], superseded: false }]);
  await page.screenshot({ path: info.outputPath("cue.png") });
  await note.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.locator("[data-cue-box]")).toHaveCount(0);
});
