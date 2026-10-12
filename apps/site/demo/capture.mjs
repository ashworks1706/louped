// The site's screenshots, in light and dark, from the demo project served by `louped serve`.
//   node apps/site/demo/capture.mjs <app url> <out dir>
// PW_CHROMIUM picks a preinstalled Chromium, as the app's own end-to-end tests do.
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";

// Playwright is installed with the app (apps/web), not the site
const require = createRequire(new URL("../../web/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const [app, out] = process.argv.slice(2);
if (!app || !out) throw new Error("usage: capture.mjs <app url> <out dir>");
const EXPERIMENT = "does-caa-steer-every-item";

const runs = await (await fetch(`${app}/api/runs`)).json();
const run = runs.find((r) => r.experiment === EXPERIMENT)?.id;
if (!run) throw new Error(`no run of ${EXPERIMENT} at ${app}: build the demo project first`);
const items = `/run/?id=${run}&tab=items&ref=none`;

/** Each shot: its file name, the page, and what to do on it before the picture. */
const SHOTS = [
  { name: "home", path: "/" },
  { name: "experiment", path: `/behavior/experiment/?name=${EXPERIMENT}` },
  { name: "launch", path: `/launch/?id=script:${EXPERIMENT}/run.py` },
  { name: "items", path: items },
  { name: "item", path: `${items}&set=open&item=0` },
  {
    name: "figure",
    path: `/run/?id=${run}&tab=figures`,
    async prepare(page) {
      const plot = page.locator(".js-plotly-plot").first();
      await plot.scrollIntoViewIfNeeded();
      await page.mouse.wheel(0, 260);
      await page.waitForTimeout(600);
      // the lowest point: the item that moves most against the multiplier
      const point = await lowestPoint(page);
      await page.mouse.move(point.x, point.y);
      await page.waitForTimeout(1200);
    },
  },
  {
    name: "picks",
    path: items,
    async prepare(page) {
      const rows = page.locator("tbody tr");
      for (const i of [1, 5, 8]) await rows.nth(i).click({ modifiers: ["Shift"] });
      await page.mouse.move(1300, 120);
      await page.waitForTimeout(600);
    },
  },
  {
    name: "column",
    path: items,
    async prepare(page) {
      // the slope column the agent derived and named
      const column = page.locator('[data-part^="items/column/"]', { hasText: "slope" }).first();
      await column.evaluate((e) => e.scrollIntoView({ block: "center" }));
      await page.waitForTimeout(600);
    },
  },
  {
    name: "chart",
    path: `/run/?id=${run}&tab=figures`,
    async prepare(page) {
      const chart = page.locator('[data-part^="figures/figure/"]', {
        hasText: "Slope by agreeing answer",
      });
      await chart.evaluate((e) => e.scrollIntoView({ block: "center" }));
      await page.mouse.move(1300, 120); // no other figure's hover
      await page.waitForTimeout(800);
    },
  },
  {
    name: "page",
    path: `/run/?id=${run}&tab=x-labels`,
    async prepare(page) {
      await page.frameLocator("iframe").first().locator("[data-label]").first().waitFor();
      await page.waitForTimeout(600);
    },
  },
];

// a few labels on the Labels page, as the researcher gives them in the video
for (const [qid, label] of [
  ["4", "letter"],
  ["6", "letter"],
  ["7", "unclear"],
]) {
  const res = await fetch(`${app}/api/x/labels/${run}/${qid}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error(`labels: ${res.status} ${await res.text()}`);
}

/** The screen position of the Plotly point with the lowest y. */
async function lowestPoint(page) {
  return page.evaluate(() => {
    const pts = [...document.querySelectorAll(".js-plotly-plot .scatterlayer .point")];
    const boxes = pts.map((p) => p.getBoundingClientRect());
    const low = boxes.reduce((a, b) => (b.y > a.y ? b : a));
    return { x: low.x + low.width / 2, y: low.y + low.height / 2 };
  });
}

await mkdir(out, { recursive: true });
const browser = await chromium.launch(
  process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
);
for (const scheme of ["light", "dark"]) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: scheme,
  });
  await context.addInitScript((s) => localStorage.setItem("theme", s), scheme);
  const page = await context.newPage();
  for (const shot of SHOTS) {
    await page.goto(app + shot.path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    if (shot.prepare) await shot.prepare(page);
    await page.screenshot({ path: `${out}/${shot.name}-${scheme}.png` });
  }
  await context.close();
}
await browser.close();
