import { API, ApiError } from "@/lib/api";

/** A run's artifact as the API serves it; each path segment encoded, the slashes kept. */
export function artifactUrl(run: string, path: string): string {
  const segments = path.split("/").map(encodeURIComponent).join("/");
  return `${API}/api/runs/${encodeURIComponent(run)}/artifacts/${segments}`;
}

/** A notebook the run logged, as the page the API draws it as. */
export function notebookUrl(run: string, path: string): string {
  const segments = path.split("/").map(encodeURIComponent).join("/");
  return `${API}/api/runs/${encodeURIComponent(run)}/notebook/${segments}`;
}

/** One artifact's text, read once per run and path. */
export const artifactQuery = (run: string, path: string) => ({
  queryKey: ["artifact", run, path],
  queryFn: async ({ signal }: { signal: AbortSignal }) => {
    const res = await fetch(artifactUrl(run, path), { signal });
    if (!res.ok) throw new ApiError(res.status, `${path}: ${res.status} ${res.statusText}`);
    return res.text();
  },
});

export type ArtifactKind =
  "markdown" | "json" | "jsonl" | "table" | "text" | "image" | "notebook" | "other";

const TEXT = /\.(txt|log|out|err|ya?ml|toml|cfg|ini|py|sh|diff|patch)$/i;

export function kindOf(path: string): ArtifactKind {
  const p = path.toLowerCase();
  if (p.endsWith(".md")) return "markdown";
  if (p.endsWith(".jsonl") || p.endsWith(".ndjson")) return "jsonl";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".csv") || p.endsWith(".tsv")) return "table";
  if (/\.(png|jpe?g|gif|svg|webp)$/.test(p)) return "image";
  if (p.endsWith(".ipynb")) return "notebook";
  if (TEXT.test(p)) return "text";
  return "other";
}

/** The text files a run logged that the server lets the app edit (louped.stores.mlflow_runs). */
export const editable = (path: string) =>
  /\.(md|txt|json|jsonl|ndjson|csv|tsv|ya?ml|toml)$/i.test(path);

/** Past this size a file is offered as a download, not read into the page. */
export const PREVIEW_BYTES = 16 * 1024 * 1024;

export type Row = Record<string, unknown>;

/** One JSON object per line; blank lines skipped, lines that do not parse counted. */
export function parseJsonl(text: string): { rows: Row[]; bad: number } {
  const rows: Row[] = [];
  let bad = 0;
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const v: unknown = JSON.parse(line);
      if (v && typeof v === "object" && !Array.isArray(v)) rows.push(v as Row);
      else rows.push({ value: v });
    } catch {
      bad += 1;
    }
  }
  return { rows, bad };
}

/** CSV or TSV with quoted fields (RFC 4180): the first row is the header. */
export function parseDelimited(text: string, sep: "," | "\t"): Row[] {
  const out: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === sep) {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      out.push(row);
      row = [];
      field = "";
    } else field += c;
  }
  if (field || row.length) {
    row.push(field);
    out.push(row);
  }
  const [header, ...body] = out.filter((r) => r.some((f) => f !== ""));
  if (!header) return [];
  return body.map((r) => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""])));
}

/** The 95% Wilson score interval for k of n, as proportions; it stays inside [0, 1] and is
 * honest at the small n and extreme rates a pilot run has, where k/n ± 1.96·SE is not. */
export function wilson(k: number, n: number, z = 1.96): [number, number] | null {
  if (n === 0) return null;
  const p = k / n;
  const z2 = z * z;
  const centre = (p + z2 / (2 * n)) / (1 + z2 / n);
  const half = (z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / (1 + z2 / n);
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

export function isScalar(v: unknown): v is string | number | boolean | null {
  return v === null || ["string", "number", "boolean"].includes(typeof v);
}

/** 0/1 and true/false both read as a pass or a fail. */
export function asBinary(v: unknown): 0 | 1 | null {
  if (v === true || v === 1) return 1;
  if (v === false || v === 0) return 0;
  return null;
}

/** More files than this in one folder are not conditions of one comparison (a folder of traces,
 * one file per request), so the Items view leaves them to Artifacts. */
export const MAX_CONDITIONS = 12;

/** Where louped derive writes a run's added per-item columns, one JSONL file each. */
export const DERIVED = "derived";

/** Folders holding two to MAX_CONDITIONS JSONL files: one file per condition, the same items in
 * each. */

export function itemFolders(paths: string[]): { dir: string; files: string[] }[] {
  const by = new Map<string, string[]>();
  for (const p of paths) {
    if (kindOf(p) !== "jsonl") continue;
    const dir = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";
    by.set(dir, [...(by.get(dir) ?? []), p]);
  }
  return (
    [...by]
      // derived/ holds columns added to the items (louped derive), not conditions
      .filter(([dir]) => dir !== DERIVED)
      .filter(([, files]) => files.length >= 2 && files.length <= MAX_CONDITIONS)
      .map(([dir, files]) => ({ dir, files: orderConditions(files) }))
      .sort((a, b) => a.dir.localeCompare(b.dir))
  );
}

const REFERENCE = /^(baseline|base|control|reference|original|unmitigated|before)$/i;

/** A baseline-like file first, since the other conditions are read against it; else by name. */
function orderConditions(files: string[]): string[] {
  const named = (f: string) => stem(f);
  return [...files].sort((a, b) => {
    const ra = REFERENCE.test(named(a)) ? 0 : 1;
    const rb = REFERENCE.test(named(b)) ? 0 : 1;
    return ra - rb || a.localeCompare(b);
  });
}

/** A file's name without its folder or extension: the condition it holds. */
export function stem(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1).replace(/\.(jsonl|ndjson)$/i, "");
}

const KEY_NAMES = [
  "id",
  "sample_id",
  "item_id",
  "qid",
  "uid",
  "key",
  "idx",
  "index",
  "question_id",
];

/** The field that names an item in every file: present in every row, scalar and unique within
 * each file. A conventional name wins; null when no field qualifies. */
export function joinKey(tables: Row[][]): string | null {
  if (tables.length === 0 || tables.some((t) => t.length === 0)) return null;
  const candidates = Object.keys(tables[0][0]).filter((k) =>
    tables.every((t) => {
      const seen = new Set<unknown>();
      for (const r of t) {
        const v = r[k];
        if (v === undefined || v === null || typeof v === "object" || typeof v === "boolean")
          return false;
        if (seen.has(v)) return false;
        seen.add(v);
      }
      return true;
    }),
  );
  return KEY_NAMES.find((n) => candidates.includes(n)) ?? candidates[0] ?? null;
}

/** Fields every file has as a scalar in its first row, in the first file's order. */
export function sharedFields(tables: Row[][], key: string): string[] {
  if (tables.length === 0 || tables[0].length === 0) return [];
  return Object.keys(tables[0][0]).filter(
    (f) => f !== key && tables.every((t) => t.length > 0 && f in t[0] && isScalar(t[0][f])),
  );
}

const OUTCOME_NAMES = ["correct", "score", "pass", "passed", "accuracy", "acc", "label", "pred"];

/** The field to compare conditions on: a conventional outcome name, else the first field that
 * is 0/1 or true/false in every row, else the first shared field. */
export function defaultField(tables: Row[][], fields: string[]): string | null {
  const named = OUTCOME_NAMES.find((n) => fields.includes(n));
  if (named) return named;
  const binary = fields.find((f) => tables.every((t) => t.every((r) => asBinary(r[f]) !== null)));
  return binary ?? fields[0] ?? null;
}

/** What an item is called in its records: a field it holds the same in every condition. */
const ITEM_NAMES = [
  "claim",
  "question",
  "prompt",
  "input",
  "statement",
  "problem",
  "instruction",
  "query",
  "text",
];

/** The item's own text (its claim, its question): a field the reference's record has and every
 * other condition that has it holds the same, so never a condition's own reply. A conventional
 * name first, else the longest that reads like text; null when the records do not say what the
 * item is. */
export function itemText(rows: (Row | undefined)[], ref: number, key: string): string | null {
  const base = rows[ref];
  if (!base) return null;
  const same = (f: string) =>
    typeof base[f] === "string" &&
    rows.every((r) => !r || !(f in r) || JSON.stringify(r[f]) === JSON.stringify(base[f]));
  const fields = Object.keys(base).filter((f) => f !== key && same(f));
  const named = ITEM_NAMES.find((n) => fields.includes(n));
  if (named) return named;
  let best: [string, number] | null = null;
  for (const f of fields) {
    const n = (base[f] as string).length;
    if (n >= 20 && (!best || n > best[1])) best = [f, n];
  }
  return best?.[0] ?? null;
}

/** Columns that split one file's records into conditions the Items view can line up: two to
 * eight scalar values (an arm, a condition, a model), each part naming an item once and the parts
 * sharing their items. */
export function splitColumns(rows: Row[]): string[] {
  if (rows.length < 2) return [];
  const columns = Object.keys(rows[0]);
  return columns.filter((c) => {
    if (!rows.every((r) => isScalar(r[c]) && r[c] !== null)) return false;
    const values = new Set(rows.map((r) => String(r[c])));
    if (values.size < 2 || values.size > 8) return false;
    const { tables } = splitBy(rows, c);
    const without = (r: Row) => Object.fromEntries(Object.entries(r).filter(([k]) => k !== c));
    const key = joinKey(tables.map((t) => t.map(without)));
    if (key === null) return false;
    // the same items under every value: an outcome column (correct: 0/1) splits items apart
    const ids = tables.map((t) => new Set(t.map((r) => String(r[key]))));
    return [...ids[0]].some((id) => ids.every((set) => set.has(id)));
  });
}

/** One file's records split by a column's values, in first-seen order. */
export function splitBy(rows: Row[], column: string): { names: string[]; tables: Row[][] } {
  const parts = new Map<string, Row[]>();
  for (const r of rows) {
    const v = String(r[column]);
    parts.set(v, [...(parts.get(v) ?? []), r]);
  }
  return { names: [...parts.keys()], tables: [...parts.values()] };
}

/** A parsed JSON file's records, when it is an array of objects. */
export function asRecords(value: unknown): Row[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  return value.every((v) => v && typeof v === "object" && !Array.isArray(v))
    ? (value as Row[])
    : null;
}

const TIME_FIELDS = ["at", "timestamp", "time", "ts", "start_time", "created_at", "started_at"];
const KIND_FIELDS = ["kind", "event", "type", "event_type", "span_kind", "name"];
const GROUP_FIELDS = ["request_id", "trace_id", "session_id", "conversation_id", "run_id"];

/** A moment from an ISO date or a number (seconds, or milliseconds when large): ms since epoch. */
export function moment(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v > 1e11 ? v : v * 1000;
  if (typeof v !== "string") return null;
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

/** How a file's records read as a trace: the field that times each event, the one naming its
 * kind, and the one grouping events into a request (null: one group). Null when they are not
 * events: no time field every row carries, or no kind field. */
export function traceShape(
  rows: Row[],
): { time: string; kind: string; group: string | null } | null {
  if (rows.length < 2) return null;
  const time = TIME_FIELDS.find((f) => rows.every((r) => moment(r[f]) !== null));
  const kind = KIND_FIELDS.find((f) => rows.every((r) => typeof r[f] === "string"));
  if (!time || !kind) return null;
  const group = GROUP_FIELDS.find((f) => rows.every((r) => isScalar(r[f]) && r[f] !== null));
  return { time, kind, group: group ?? null };
}

/** A value as one short line for a table cell. */
export function brief(v: unknown, max = 120): string {
  if (v === undefined) return "";
  if (v === null) return "null";
  if (typeof v === "string") return v.length > max ? `${v.slice(0, max)}…` : v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) {
    const s = JSON.stringify(v);
    return s.length > max ? `[${v.length} items]` : s;
  }
  const s = JSON.stringify(v);
  return s.length > max ? `{${Object.keys(v as object).length} fields}` : s;
}

/** Rows as a file the person can keep: JSONL, one object per line. */
export function downloadJsonl(rows: Row[], name: string): void {
  const blob = new Blob([rows.map((r) => JSON.stringify(r)).join("\n") + "\n"], {
    type: "application/x-ndjson",
  });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0); // revoked in the same tick, Firefox drops it
}
