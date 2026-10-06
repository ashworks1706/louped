// Record the demo, from install to result: a researcher installs louped, makes a project and
// starts the app in a terminal, then asks their coding agent a question and works through the
// answer in the app.
//   node apps/site/demo/record.mjs <out dir>
// Everything on screen is real except the agent's words. The terminal commands run here and
// their output is theirs (only the scratch folder reads as ~/research). The app is a fresh
// `louped init` served by this script; every page, number and pointer the agent puts on screen
// goes through the same API its tools call (new_experiment, launch, ui_show, ui_selection,
// save_cohort), and the run is the experiment's own. The agent's side of the conversation is
// scripted: its lines are written here, and render.py draws them in a panel beside the app.
// Saves the browser's frames (frames/*.jpg) and timeline.json.
import { execFile, spawn } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

// Playwright is installed with the app (apps/web), not the site
const require = createRequire(new URL("../../web/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const [out] = process.argv.slice(2);
if (!out) throw new Error("usage: record.mjs <out dir>");
const LOUPED = process.env.LOUPED ?? "louped";
const PORT = 8000;
const app = `http://127.0.0.1:${PORT}`;
const EXPERIMENT = "does-caa-steer-every-item";
const VIEW = { width: 1440, height: 900 };
const run = promisify(execFile);

const work = await mkdtemp(join(tmpdir(), "louped-demo-"));
const project = join(work, "sycophancy");
const tidy = (text) => text.replaceAll(work, "~/research").trimEnd();

await mkdir(`${out}/frames`, { recursive: true });

// the timeline, in seconds of wall time (CDP's frame clock)
const now = () => Date.now() / 1000;
const start = now();
const frames = [];
const pointer = [];
const clicks = [];
const camera = [];
const chat = [];
const term = [];
const screens = [];
const urls = [];
const speed = [];
let at = { x: VIEW.width / 2, y: VIEW.height / 2 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 1. the terminal: each command is typed, run for real, and its output shown
let prompt = "~/research";
async function shell(cmd, exec, { keep = () => true } = {}) {
  term.push({ t: now(), kind: "cmd", prompt, text: cmd });
  await sleep(500 + cmd.length * 45);
  const output = await exec();
  const lines = tidy(output).split("\n").filter(keep);
  term.push({ t: now(), kind: "out", text: lines.join("\n") });
  await sleep(700 + Math.min(lines.length, 16) * 110);
}
screens.push({ t: now(), screen: "terminal" });
await sleep(900);

const tools = join(work, ".uv");
await shell(
  "uv tool install louped",
  async () => {
    const env = { ...process.env, UV_TOOL_DIR: tools, UV_TOOL_BIN_DIR: join(tools, "bin") };
    const { stdout, stderr } = await run("uv", ["tool", "install", "louped"], { env });
    return stdout + stderr;
  },
  { keep: (l) => !l.startsWith(" + ") && !l.startsWith("warning:") },
); // the package list
await shell(
  "louped init sycophancy",
  async () => (await run(LOUPED, ["init", "sycophancy"], { cwd: work })).stdout,
);
await shell("cd sycophancy && cat .mcp.json", async () => {
  prompt = "~/research/sycophancy";
  return readFile(join(project, ".mcp.json"), "utf8");
});

term.push({ t: now(), kind: "cmd", prompt, text: "louped serve" });
await sleep(500 + "louped serve".length * 45);
const server = spawn(LOUPED, ["serve", "--port", String(PORT)], { cwd: project });
let log = "";
server.stdout.on("data", (d) => (log += d));
server.stderr.on("data", (d) => (log += d));
process.on("exit", () => server.kill());
while (!log.includes("Uvicorn running")) await sleep(200);
const served = log
  .split("\n")
  .filter((l) => l.startsWith("INFO:") && !l.includes('"GET'))
  .join("\n");
term.push({ t: now(), kind: "out", text: tidy(served) });
await sleep(2200);

// 2. the app, beside the agent
const browser = await chromium.launch(
  process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
);
const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2 });
await context.addInitScript(() => localStorage.setItem("theme", "light"));
const page = await context.newPage();
page.on("framenavigated", (f) => {
  if (f === page.mainFrame()) urls.push({ t: now(), url: f.url().replace(app, "") || "/" });
});
const cdp = await context.newCDPSession(page);
cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const file = `frames/${String(frames.length).padStart(5, "0")}.jpg`;
  frames.push({ t: metadata.timestamp, file });
  await writeFile(`${out}/${file}`, Buffer.from(data, "base64"));
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});

const wait = (ms) => page.waitForTimeout(ms);
const ease = (u) => (u < 0.5 ? 4 * u ** 3 : 1 - (-2 * u + 2) ** 3 / 2);
const api = async (method, path, body) => {
  const r = await fetch(`${app}/api${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body && JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status} ${await r.text()}`);
  return r.json();
};

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
  await locator.scrollIntoViewIfNeeded().catch(async (err) => {
    await page.screenshot({ path: `${out}/failed.png` });
    throw err;
  });
  const b = await locator.boundingBox();
  if (!b) throw new Error(`not on screen: ${locator}`);
  return { x: b.x + b.width / 2, y: b.y + b.height / 2, b };
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
/** Bring the pointer to the start of a thing, as the eye goes to it, and close in on it. */
async function follow(locator, scale, { ms = 800 } = {}) {
  const { x, y, b } = await centre(locator);
  await glide(Math.min(b.x + 24, x), y, ms);
  look(scale, x, y);
}

/** A line in the agent panel; waits as long as it takes to type (you) or stream (agent). */
async function say(who, text) {
  chat.push({ t: now(), who, text });
  const perChar = { you: 34, agent: 14, tool: 0, note: 0 }[who];
  await wait(400 + text.length * perChar);
}
const you = (text) => say("you", text);
const agent = (text) => say("agent", text);
const tool = (text) => say("tool", text);

/** What the agent's ui_show does: the app opens the page and points at the parts. */
async function show(url, parts = [], text = null) {
  await api("POST", "/ui/show", { url, parts, text, style: "highlight" });
  const path = url.split("?")[0];
  await page.waitForURL((u) => u.pathname === path, { timeout: 8000 });
  await page.waitForLoadState("networkidle");
  await wait(900);
}

/** A job through the queue, as launch does; resolves when it ends. */
async function job(body) {
  const { id } = await api("POST", "/launch", body);
  for (;;) {
    const j = await api("GET", `/launch/jobs/${id}`);
    if (j.status === "succeeded") return j;
    if (["failed", "cancelled"].includes(j.status)) throw new Error(`job ${id} ${j.status}`);
    await sleep(500);
  }
}

await page.goto(`${app}/`);
await page.waitForLoadState("networkidle");
await page.mouse.move(at.x, at.y);
await cdp.send("Page.startScreencast", {
  format: "jpeg",
  quality: 92,
  maxWidth: 2880,
  maxHeight: 1800,
});
await wait(300);
screens.push({ t: now(), screen: "app" });
pointer.push({ t: now(), ...at });
look(1);
await say("note", "louped mcp connected · reads AGENTS.md");
await glide(220, 300, 900); // the sidebar: a fresh project, with louped's example
await wait(900);

// 3. the question
await you(
  "Does CAA's sycophancy vector move every item, or only the mean? Use their released Llama 2 7B results.",
);
await tool(`new_experiment ${EXPERIMENT}`);
await job({ id: "new", options: { name: EXPERIMENT, "--domain": "conditioning" } });
const folder = join(project, "experiments", EXPERIMENT);
// the README the agent writes first stops at Run; Result and Next come once it has them
const readme = await readFile(new URL(`./${EXPERIMENT}/README.md`, import.meta.url), "utf8");
await writeFile(join(folder, "README.md"), readme.split("\n## Result")[0] + "\n");
await tool(`write ${EXPERIMENT}/README.md`);
await cp(new URL(`./${EXPERIMENT}/run.py`, import.meta.url), join(folder, "run.py"));
await tool(`write ${EXPERIMENT}/run.py`);
await agent(
  "The README states the question and three hypotheses. run.py reads the result files CAA released, at a pinned commit, so no model runs and no GPU is needed.",
);
const experiment = `/behavior/experiment/?name=${EXPERIMENT}`;
await show(experiment, [], "The question, its hypotheses and the test.");
await follow(page.getByRole("heading", { name: EXPERIMENT }), 1.45);
await wait(2000);
await follow(page.getByRole("heading", { name: "Hypotheses" }), 1.4);
await wait(2400);
look(1);

// 4. the run, sped up while it works
await you("Run it.");
await tool(`launch script:${EXPERIMENT}/run.py`);
const { id: jobId } = await api("POST", "/launch", { id: `script:${EXPERIMENT}/run.py` });
await show(`/job/?id=${jobId}`, [], "It fetches CAA's files and logs each condition.");
await glide(VIEW.width / 2 + 120, 420, 700);
const fast = { t0: now() + 1.5, rate: 8 };
for (;;) {
  const j = await api("GET", `/launch/jobs/${jobId}`);
  if (j.status === "succeeded") break;
  if (["failed", "cancelled"].includes(j.status)) throw new Error(`run.py ${j.status}`);
  await sleep(500);
}
await wait(1500);
speed.push({ ...fast, t1: now() - 1 });
const runId = (await api("GET", "/runs")).find((r) => r.experiment === EXPERIMENT)?.id;
if (!runId) throw new Error("run.py logged no run");

await agent(
  "Done. Mean P(agree) is 0.54 with the vector subtracted, 0.69 with none and 0.62 with it added. At layer 13, adding it does not raise the mean.",
);
await show(
  `/run/?id=${runId}&tab=items&ref=none`,
  ["items/summary"],
  "Each condition against none.",
);
await follow(page.locator('[data-part="items/summary"]'), 1.25);
await wait(2600);
look(1);

// 5. the items the mean hides
await agent("Item by item, 22 of 50 move against the multiplier.");
const figures = `/run/?id=${runId}&tab=figures`;
await page.goto(app + figures); // to find the figure's address, which names its file
await page.waitForLoadState("networkidle");
const figure = await page.evaluate(
  () =>
    [...document.querySelectorAll('[data-part^="figures/figure/"]')].find((e) =>
      e.textContent.includes("Slope per item"),
    )?.dataset.part,
);
if (!figure) throw new Error("no Slope per item figure on the run");
await show(figures, [figure], "Below zero: the vector moves the item the wrong way.");
const plot = page.locator(`[data-part="${figure}"] .js-plotly-plot`);
await plot.scrollIntoViewIfNeeded();
await wait(600);
const low = await plot.evaluate((el) => {
  const pts = [...el.querySelectorAll(".scatterlayer .point")];
  const b = pts.map((p) => p.getBoundingClientRect()).reduce((a, c) => (c.y > a.y ? c : a));
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
});
await glide(low.x, low.y, 1100);
look(1.3, low.x - 120, low.y - 40);
await wait(2600);
look(1);

// 6. the researcher picks three and asks why
await click(page.getByRole("tab", { name: "Items" }));
await page.waitForLoadState("networkidle");
await wait(800);
const rows = page.locator("tbody tr");
// bring the rows to the middle, clear of the tray that the first pick opens
await rows.nth(5).evaluate((e) => e.scrollIntoView({ block: "center", behavior: "smooth" }));
await wait(900);
const tray = page.locator("[data-part-tray]");
for (const [n, i] of [4, 6, 7].entries()) {
  await click(rows.nth(i).locator("td").nth(1), { shift: true, ms: 500 });
  await tray
    .getByText(`${n + 1} picked`)
    .waitFor({ timeout: 3000 })
    .catch(async (err) => {
      await page.screenshot({ path: `${out}/failed.png` });
      throw err;
    });
}
await wait(400);
const { x: tx, y: ty } = await centre(tray);
await glide(tx - 120, ty, 700);
look(1.4, tx, ty - 60);
await you("@sel why do these move the wrong way?");
look(1);
// what ui_selection does: it reads the picks, and the tray says so
const picks = await api("GET", "/ui/selection");
if (picks?.parts?.length !== 3)
  throw new Error(`expected 3 picks, the app has ${picks?.parts?.length}`);
await api("POST", "/ui/selection/read", { version: picks.version });
await tool("ui_selection: 3 picks");
await agent(
  "All three have the agreeing answer at (A), and each moves against the multiplier (slopes -0.12, -0.20, -0.36). Of the 22 items that do, 21 are (A). The vector may carry the answer letter, not only agreement.",
);
await api("PUT", `/experiments/${EXPERIMENT}/cohorts/letter-a`, {
  ids: ["4", "6", "7"],
  note: "Agreeing answer at (A); each moves against the multiplier.",
  run: runId,
  folder: "ab",
});
await tool("save_cohort letter-a");
await wait(800);

// 7. what to test next
await you("What would settle it?");
await agent(
  "Swap A and B on every item and steer again. If the slopes follow the letter, the vector carries the letter. I wrote the result and this next step into the README.",
);
await writeFile(join(folder, "README.md"), readme);
await tool(`edit ${EXPERIMENT}/README.md: Result, Next`);
// Escape closes the agent's note first, then drops the picks
await page.keyboard.press("Escape");
await page.keyboard.press("Escape");
await show(experiment, ["experiment.design/readme"], "The next test.");
await follow(page.getByRole("heading", { name: "Next", exact: true }), 1.4);
await wait(3400);
look(1);
await wait(1200);

await cdp.send("Page.stopScreencast");
await wait(300);
const rel = (xs) => xs.map((x) => ({ ...x, t: x.t - start }));
const timeline = {
  view: VIEW,
  scale: 2,
  duration: now() - start,
  frames: rel(frames),
  pointer: rel(pointer),
  clicks: rel(clicks),
  camera: rel(camera),
  chat: rel(chat),
  term: rel(term),
  screens: rel(screens),
  urls: rel(urls),
  speed: speed.map((s) => ({ ...s, t0: s.t0 - start, t1: s.t1 - start })),
};
await writeFile(`${out}/timeline.json`, JSON.stringify(timeline));
await browser.close();
server.kill();
console.log(`${frames.length} frames over ${timeline.duration.toFixed(1)} s`);
