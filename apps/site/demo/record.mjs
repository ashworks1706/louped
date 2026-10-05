// Record the demo: a researcher asks their coding agent a question and works through the answer
// in the app.
//   node apps/site/demo/record.mjs <app url> <out dir>
// The app is real: every page, number and pointer the agent puts on screen comes from the demo
// project, through the same API the agent's tools call (ui_show, save_cohort). The agent's side
// of the conversation is scripted: its lines are written here, and render.py draws them in a
// panel beside the app. It saves the browser's own frames (frames/*.jpg) and timeline.json.
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";

// Playwright is installed with the app (apps/web), not the site
const require = createRequire(new URL("../../web/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const [app, out] = process.argv.slice(2);
if (!app || !out) throw new Error("usage: record.mjs <app url> <out dir>");
const EXPERIMENT = "does-caa-steer-every-item";
const VIEW = { width: 1440, height: 900 };

const runs = await (await fetch(`${app}/api/runs`)).json();
const run = runs.find((r) => r.experiment === EXPERIMENT)?.id;
if (!run) throw new Error(`no run of ${EXPERIMENT} at ${app}: build the demo project first`);
const pages = {
  experiment: `/behavior/experiment/?name=${EXPERIMENT}`,
  items: `/run/?id=${run}&tab=items&ref=none`,
  figures: `/run/?id=${run}&tab=figures`,
};

await mkdir(`${out}/frames`, { recursive: true });
const browser = await chromium.launch(
  process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
);
const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2 });
await context.addInitScript(() => localStorage.setItem("theme", "light"));
const page = await context.newPage();

// the timeline, in seconds of wall time (CDP's frame clock)
const now = () => Date.now() / 1000;
const frames = [];
const pointer = [];
const clicks = [];
const camera = [];
const chat = [];
let at = { x: VIEW.width / 2, y: VIEW.height / 2 };

const cdp = await context.newCDPSession(page);
cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const file = `frames/${String(frames.length).padStart(5, "0")}.jpg`;
  frames.push({ t: metadata.timestamp, file });
  await writeFile(`${out}/${file}`, Buffer.from(data, "base64"));
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});

const wait = (ms) => page.waitForTimeout(ms);
const ease = (u) => (u < 0.5 ? 4 * u ** 3 : 1 - (-2 * u + 2) ** 3 / 2);

/** Glide the pointer to (x, y), as a hand would, logging each step. */
async function glide(x, y, ms = 700) {
  const from = at;
  const steps = Math.max(2, Math.round(ms / 16));
  for (let i = 1; i <= steps; i++) {
    const u = ease(i / steps);
    at = { x: from.x + (x - from.x) * u, y: from.y + (y - from.y) * u };
    await page.mouse.move(at.x, at.y);
    pointer.push({ t: now(), ...at });
    await wait(16);
  }
}

async function centre(locator) {
  await locator.scrollIntoViewIfNeeded();
  const b = await locator.boundingBox();
  if (!b) throw new Error(`not on screen: ${locator}`);
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

async function click(locator, { shift = false, ms = 600 } = {}) {
  const { x, y } = await centre(locator);
  await glide(x, y, ms);
  await wait(120);
  clicks.push({ t: now(), x, y });
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.click(x, y);
  if (shift) await page.keyboard.up("Shift");
}

/** Point the camera: scale 1 shows the whole window; above 1 closes in on (x, y). */
const look = (scale, x = VIEW.width / 2, y = VIEW.height / 2) =>
  camera.push({ t: now(), scale, x, y });
const lookAt = async (locator, scale) => {
  const { x, y } = await centre(locator);
  look(scale, x, y);
};

/** A line in the agent panel; waits as long as it takes to type (you) or stream (agent). */
async function say(who, text) {
  chat.push({ t: now(), who, text });
  const perChar = { you: 34, agent: 14, tool: 0 }[who];
  await wait(400 + text.length * perChar);
}
const you = (text) => say("you", text);
const agent = (text) => say("agent", text);
const tool = (text) => say("tool", text);

/** What the agent's ui_show does: the app opens the page and points at the parts. */
async function show(url, parts = [], text = null) {
  const r = await fetch(`${app}/api/ui/show`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, parts, text, style: "highlight" }),
  });
  if (!r.ok) throw new Error(`ui_show: ${r.status} ${await r.text()}`);
  const path = url.split("?")[0];
  await page.waitForURL((u) => u.pathname === path, { timeout: 8000 });
  await page.waitForLoadState("networkidle");
  await wait(900);
}

/** The address of the first part of a kind whose text holds some words. */
const partWith = (prefix, words) =>
  page.evaluate(
    ([p, w]) =>
      [...document.querySelectorAll(`[data-part^="${p}"]`)].find((e) => e.textContent.includes(w))
        ?.dataset.part,
    [prefix, words],
  );

await page.goto(`${app}/`);
await page.waitForLoadState("networkidle");
await wait(600);
await cdp.send("Page.startScreencast", {
  format: "jpeg",
  quality: 92,
  maxWidth: 2880,
  maxHeight: 1800,
});
const start = now();
look(1);
await wait(700);

// 1. the question
await you(
  "Does CAA's sycophancy vector move every item, or only the mean? Use their released Llama 2 7B results.",
);
await tool(`new_experiment ${EXPERIMENT}`);
await agent(
  "I wrote the question, three hypotheses and a run.py. It reads the result files CAA released, at a pinned commit, so no model runs.",
);
await show(pages.experiment);
await lookAt(page.getByRole("heading", { name: EXPERIMENT }), 1.45);
await wait(2600);
look(1);

// 2. the run, condition by condition
await tool("launch script:does-caa-steer-every-item/run.py");
await agent(
  "Done. Mean P(agree) is 0.54 with the vector subtracted, 0.69 with none and 0.62 with it added. At layer 13, adding it does not raise the mean.",
);
await show(pages.items, ["items/summary"], "Each condition against none, with its interval.");
await lookAt(page.locator('[data-part="items/summary"]'), 1.25);
await wait(2600);
look(1);

// 3. the items the mean hides
await agent("Item by item, 22 of 50 move against the multiplier.");
await page.goto(app + pages.figures); // to find the figure's address, which names its file
await page.waitForLoadState("networkidle");
const figure = await partWith("figures/figure/", "Slope per item");
if (!figure) throw new Error("no Slope per item figure on the run");
await show(pages.figures, [figure], "Below zero: the vector moves the item the wrong way.");
const plot = page.locator(".js-plotly-plot").first();
await plot.scrollIntoViewIfNeeded();
await wait(600);
const low = await page.evaluate(() => {
  const pts = [...document.querySelectorAll(".js-plotly-plot .scatterlayer .point")];
  const b = pts.map((p) => p.getBoundingClientRect()).reduce((a, c) => (c.y > a.y ? c : a));
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
});
look(1.3, low.x - 120, low.y + 30);
await glide(low.x, low.y, 1100);
await wait(2600);
look(1);

// 4. the researcher picks three and asks why
await click(page.getByRole("tab", { name: "Items" }));
await page.waitForLoadState("networkidle");
await wait(800);
const rows = page.locator("tbody tr");
const tray = page.locator("[data-part-tray]");
for (const [n, i] of [4, 6, 7].entries()) {
  await click(rows.nth(i).locator("td").nth(1), { shift: true, ms: 500 });
  await tray.getByText(`${n + 1} picked`).waitFor({ timeout: 3000 });
}
await wait(600);
await lookAt(page.getByText(/picked/).first(), 1.4);
await you("@sel why do these move the wrong way?");
look(1);
// what the agent's ui_selection does: it reads the picks, and the tray says so
const picks = await (await fetch(`${app}/api/ui/selection`)).json();
if (picks?.parts?.length !== 3)
  throw new Error(`expected 3 picks, the app has ${picks?.parts?.length}`);
await fetch(`${app}/api/ui/selection/read`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ version: picks.version }),
});
await tool("ui_selection: 3 picks");
await agent(
  "All three have the agreeing answer at (A), and each moves against the multiplier (slopes -0.12, -0.20, -0.36). Of the 22 items that do, 21 are (A). The vector may carry the answer letter, not only agreement.",
);
const saved = await fetch(`${app}/api/experiments/${EXPERIMENT}/cohorts/letter-a`, {
  method: "PUT",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    ids: ["4", "6", "7"],
    note: "Agreeing answer at (A); each moves against the multiplier.",
    run,
    folder: "ab",
  }),
});
if (!saved.ok) throw new Error(`save_cohort: ${saved.status} ${await saved.text()}`);
await tool("save_cohort letter-a");
await wait(800);

// 5. what to test next
await you("What would settle it?");
await agent(
  "Swap A and B on every item and steer again. If the slopes follow the letter, the vector carries the letter. It is the README's next step.",
);
// Escape closes the agent's note first, then drops the picks
await page.keyboard.press("Escape");
await page.keyboard.press("Escape");
await show(pages.experiment, ["experiment.design/readme"], "The next test is in the README.");
await lookAt(page.getByRole("heading", { name: "Next", exact: true }), 1.4);
await wait(3400);
look(1);
await wait(1500);

await cdp.send("Page.stopScreencast");
await wait(300);
const rel = (xs) => xs.map((x) => ({ ...x, t: x.t - start }));
const timeline = {
  view: VIEW,
  scale: 2,
  duration: now() - start,
  frames: rel(frames).filter((f) => f.t > -1),
  pointer: rel(pointer),
  clicks: rel(clicks),
  camera: rel(camera),
  chat: rel(chat),
};
await writeFile(`${out}/timeline.json`, JSON.stringify(timeline));
await browser.close();
console.log(`${frames.length} frames over ${timeline.duration.toFixed(1)} s`);
