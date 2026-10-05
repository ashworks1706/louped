// Record the demo: one pass through the demo project in the app, as a person would click it.
//   node apps/site/demo/record.mjs <app url> <out dir>
// It saves the browser's own frames (frames/*.jpg) and timeline.json: each frame's time, where the
// pointer was, each click, and where the camera should look. render.py turns them into the video.
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

await mkdir(`${out}/frames`, { recursive: true });
const browser = await chromium.launch(
  process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
);
const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2 });
await context.addInitScript(() => localStorage.setItem("theme", "light"));
const page = await context.newPage();

// the timeline, in seconds from the first frame's clock (CDP's, which is wall time)
const now = () => Date.now() / 1000;
const frames = [];
const pointer = [];
const clicks = [];
const camera = [];
const captions = [];
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

/** The centre of an element, in the page's CSS pixels. */
async function centre(locator) {
  await locator.scrollIntoViewIfNeeded();
  const b = await locator.boundingBox();
  if (!b) throw new Error(`not on screen: ${locator}`);
  return { x: b.x + b.width / 2, y: b.y + b.height / 2, b };
}

async function click(locator, { shift = false, ms = 700 } = {}) {
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
const say = (text) => captions.push({ t: now(), text });

await page.goto(`${app}/behavior/experiment/?name=${EXPERIMENT}`);
await page.waitForLoadState("networkidle");
await wait(500);
await cdp.send("Page.startScreencast", {
  format: "jpeg",
  quality: 92,
  maxWidth: 2880,
  maxHeight: 1800,
});
const start = now();
look(1);
await wait(600);

// 1. the question
say("An experiment is a question, a plan and a script");
await lookAt(page.getByRole("heading", { name: EXPERIMENT }), 1.6);
await glide(520, 160, 900);
await wait(2600);
look(1);
await wait(700);

// 2. its run, item by item
say("Every run keeps each item under every condition");
await click(page.getByRole("tab", { name: /Runs/ }));
await wait(900);
await click(page.getByRole("link", { name: /released results/ }).first());
await page.waitForLoadState("networkidle");
await wait(800);
await click(page.getByRole("tab", { name: "Items" }));
await page.waitForLoadState("networkidle");
await wait(900);
const against = page.locator(
  'select[data-part="items/against"], [data-part="items/against"] select',
);
await click(against);
await against.selectOption("none");
await wait(700);
await lookAt(page.locator('[data-part="items/summary"]'), 1.2);
say("Each condition against the reference, with paired intervals");
await glide(980, 420, 900);
await wait(3000);
look(1);
await wait(600);

// 3. pick items for the agent
say("Shift+click any rows: your agent sees what you picked");
const rows = page.locator("tbody tr");
for (const i of [1, 2, 3]) await click(rows.nth(i).locator("td").nth(1), { shift: true, ms: 500 });
await wait(500);
const tray = page.getByText(/picked/).first();
await lookAt(tray, 1.5);
await wait(2600);
await click(page.getByRole("button", { name: "Clear" }));
look(1);
await wait(700);

// 4. what the model said
say("Open an item to read each condition side by side");
const records = page.locator('[data-part="items/records"] select');
await click(records);
await records.selectOption("open");
await page.waitForLoadState("networkidle");
await wait(900);
await click(page.locator("tbody tr").first().locator("td").nth(1));
await wait(1200);
look(1.18, 900, 330);
await glide(560, 420, 1200);
await wait(1800);
await glide(1240, 420, 1600);
await wait(2200);
look(1);
await page.keyboard.press("Escape");
await wait(700);

// 5. a figure traced to its rows
say("Hover any point to trace it to its item, files and script");
await click(page.getByRole("tab", { name: "Figures" }));
await page.waitForLoadState("networkidle");
await wait(1200);
const plot = page.locator(".js-plotly-plot").first();
await plot.scrollIntoViewIfNeeded();
await page.mouse.wheel(0, 300);
await wait(900);
const low = await page.evaluate(() => {
  const pts = [...document.querySelectorAll(".js-plotly-plot .scatterlayer .point")];
  const b = pts.map((p) => p.getBoundingClientRect()).reduce((a, c) => (c.y > a.y ? c : a));
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
});
look(1.3, low.x - 120, low.y + 30);
await glide(low.x, low.y, 1100);
await wait(2800);
say("Click it to open the item");
clicks.push({ t: now(), ...low });
await page.mouse.click(low.x, low.y);
await wait(1600);
look(1);
await wait(2200);

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
  captions: rel(captions),
};
await writeFile(`${out}/timeline.json`, JSON.stringify(timeline));
await browser.close();
console.log(`${frames.length} frames over ${timeline.duration.toFixed(1)} s`);
