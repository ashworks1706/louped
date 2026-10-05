// louped's kit for plugin pages: which run or experiment the page is on, the API, and the app's
// cards built from data. Import it as a module:
//
//   <link rel="stylesheet" href="/kit/louped.css" />
//   <script type="module">
//     import { api, run, stats } from "/kit/louped.js";
//     const r = await api(`/runs/${run}`);
//     document.body.append(stats(Object.entries(r.metrics)));
//   </script>
//
// A page shown as a block in a layout grows its frame to fit what it draws.

const params = new URLSearchParams(location.search);
/** The run the page is on (a run tab or block), else null. */
export const run = params.get("run");
/** The experiment the page is on, else null. */
export const experiment = params.get("experiment");
// a block in a layout sits in the app's own frame, with no border or padding of its own
if (params.has("block")) document.documentElement.setAttribute("data-block", "");

/** GET (or init's method) /api<path> as JSON; a failure throws the server's own message. */
export async function api(path, init = {}) {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init.headers },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail ?? `${res.status} /api${path}`);
  return body;
}

/** An element: h("p", { class: "l-muted" }, "text", child). */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else el.setAttribute(k, v);
  }
  el.append(...children.flat().filter((c) => c != null));
  return el;
}

const fmt = (v) =>
  typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toPrecision(3)) : String(v ?? "—");

/** Numbers as the app's metric cards: [[label, value, note?], ...]. */
export function stats(items) {
  return h(
    "div",
    { class: "l-stats" },
    items.map(([label, value, note]) =>
      h("div", { class: "l-stat" }, h("span", {}, label), h("span", {}, fmt(value)),
        note == null ? null : h("span", {}, note)),
    ),
  );
}

/** Records as the app's tables, numbers right-aligned; columns default to the first row's keys. */
export function table(rows, columns = Object.keys(rows[0] ?? {})) {
  const cell = (tag, v) =>
    h(tag, typeof v === "number" ? { class: "l-num" } : {}, tag === "th" ? v : fmt(v));
  return h(
    "table",
    { class: "l-table" },
    h("thead", {}, h("tr", {}, columns.map((c) => cell("th", c)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, columns.map((c) => cell("td", r[c]))))),
  );
}

/** What fills an empty block: a line saying what would. */
export const empty = (text) => h("p", { class: "l-empty" }, text);

// Tell the app this page's height, so a block's frame fits it.
if (window.parent !== window) {
  const tell = () =>
    window.parent.postMessage(
      { type: "louped:height", height: document.documentElement.scrollHeight },
      location.origin,
    );
  new ResizeObserver(tell).observe(document.documentElement);
}
