"use client";

import { useQueries } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";

import { Help } from "@/components/help";
import { Markdown } from "@/components/markdown";
import { part, partId, PartData } from "@/components/parts";
import { PlotlyFigure } from "@/components/plotly-figure";
import { VegaFigure } from "@/components/vega-figure";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  q,
  type BoardControl,
  type BoardFilter,
  type BoardPanel,
  type BoardView,
  type PlotlyView,
  type VegaView,
} from "@/lib/api";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

type Row = Record<string, unknown>;
type Value = string | number | boolean | (string | number | boolean)[] | null;
type Params = Record<string, Value>;
type Loaded = { rows: Row[]; columns: string[]; truncated: boolean; error: string | null };

/** No rows, the same array each render, so a panel without its table does not redraw. */
const EMPTY: Row[] = [];
const EMPTY_COLUMNS: string[] = [];
/** Rows a table shows before "Show all": a board draws in the browser. */
const PAGE = 200;
const SPAN: Record<number, string> = {
  1: "md:col-span-1",
  2: "md:col-span-2",
  3: "md:col-span-3",
  4: "md:col-span-4",
};

/** A board: tables, controls and panels that follow each other. A control, or a click on a
 * panel's mark, row or node, sets a param; each panel filtered by it redraws. Its params last
 * while the page is open. */
export function BoardFigure({ view, name }: { view: BoardView; name: string }) {
  const tables = useTables(view);
  const [params, setParams] = useState<Params>(() =>
    Object.fromEntries(view.controls.map((c) => [c.id, (c.default ?? null) as Value])),
  );
  const set = (param: string, value: Value) => setParams((p) => ({ ...p, [param]: value }));
  // a click on what is already picked lets it go
  const pick = (param: string, value: string) =>
    setParams((p) => ({ ...p, [param]: p[param] === value ? null : value }));
  const picked = view.panels
    .map((p) => p.select?.param)
    .filter((p): p is string => !!p && !view.controls.some((c) => c.id === p))
    .filter((p, i, all) => all.indexOf(p) === i && params[p] != null);
  const shown = (p: BoardPanel) =>
    (p.data ? (tables[p.data]?.rows ?? []) : []).filter((r) =>
      (p.where ?? []).every((f) => keep(r, f, params)),
    );
  return (
    <div className="flex flex-col gap-4">
      <PartData
        prefix={`board/${encodeURIComponent(name)}`}
        resolve={(pid) => {
          const id = decodeURIComponent(pid.split("/").at(-1) ?? "");
          const panel = view.panels.find((p) => p.id === id);
          if (panel) return { ...panel, rows: shown(panel).slice(0, 50), params };
          const control = view.controls.find((c) => c.id === id);
          return control ? { ...control, value: params[control.id] } : null;
        }}
      />
      {(view.controls.length > 0 || picked.length > 0) && (
        <div className="flex flex-wrap items-end gap-3">
          {view.controls.map((c) => (
            <Control
              key={c.id}
              control={c}
              id={partId(`board/${encodeURIComponent(name)}/control`, c.id)}
              value={params[c.id] ?? null}
              options={options(c, tables)}
              onChange={(v) => set(c.id, v)}
            />
          ))}
          {picked.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => set(p, null)}
              {...part(partId(`board/${encodeURIComponent(name)}/control`, p))}
              className="bg-accent hover:bg-accent/70 flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm"
              aria-label={`Clear ${p}`}
            >
              <span className="text-muted-foreground">{p}</span>
              <span className="font-mono">{String(params[p])}</span>
              <X className="size-3.5" />
            </button>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {view.panels.map((p) => {
          const table = p.data ? tables[p.data] : undefined;
          return (
            <section
              key={p.id}
              {...part(partId(`board/${encodeURIComponent(name)}/panel`, p.id))}
              className={cn("flex min-w-0 flex-col rounded-lg border", SPAN[p.span ?? 2])}
            >
              {(p.title || p.about) && (
                <header className="flex items-center gap-1.5 border-b px-3 py-2 text-sm font-medium">
                  {p.title}
                  {p.about && <Help label={`How to read ${p.title ?? p.id}`}>{p.about}</Help>}
                </header>
              )}
              <div className="min-w-0 flex-1 p-3">
                {table === undefined && p.data ? (
                  <Skeleton className="h-24 w-full" />
                ) : table?.error ? (
                  <p className="text-negative text-sm">{table.error}</p>
                ) : (
                  <Panel
                    panel={p}
                    source={table?.rows ?? EMPTY}
                    columns={table?.columns ?? EMPTY_COLUMNS}
                    edges={(p.edges && tables[p.edges]?.rows) || EMPTY}
                    params={params}
                    onPick={(v) => p.select && pick(p.select.param, v)}
                  />
                )}
                {table?.truncated && (
                  <p className="text-muted-foreground mt-2 text-xs">
                    Only the first {table.rows.length.toLocaleString()} rows are read.
                  </p>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

/** Each table by name: inline rows as they are, a ref read from louped (again every `live`
 * seconds); undefined while it loads. */
function useTables(view: BoardView): Record<string, Loaded | undefined> {
  const named = Object.entries(view.data);
  const refs = named.filter(([, d]) => d.ref);
  const reads = useQueries({
    queries: refs.map(([, d]) => q.boardTable(d.ref!, d.live)),
  });
  const out: Record<string, Loaded | undefined> = {};
  for (const [table, d] of named) {
    if (d.rows) {
      const columns = [...new Set(d.rows.flatMap((r) => Object.keys(r)))];
      out[table] = { rows: d.rows, columns, truncated: false, error: null };
    }
  }
  refs.forEach(([table], i) => {
    const r = reads[i];
    if (r.data) out[table] = { ...r.data, error: null };
    else if (r.error)
      out[table] = { rows: [], columns: [], truncated: false, error: r.error.message };
  });
  return out;
}

/** Whether a row passes a filter; a param not set (none, "", []) passes every row. The server
 * checks a board the same way (louped.stores.boards.keep). */
function keep(row: Row, f: BoardFilter, params: Params): boolean {
  const want = (f.param ? params[f.param] : f.value) as Value | undefined;
  if (want == null || want === "" || (Array.isArray(want) && want.length === 0)) return true;
  const got = row[f.field];
  const op = f.op ?? "==";
  if (op === "in") return (Array.isArray(want) ? want : [want]).some((w) => text(w) === text(got));
  if (op === "contains")
    return String(got ?? "")
      .toLowerCase()
      .includes(String(want).toLowerCase());
  if (Array.isArray(want)) return false;
  if (op === "==" || op === "!=") return (text(got) === text(want)) === (op === "==");
  const a = number(got);
  const b = number(want);
  if (a === null || b === null) return false;
  return { "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b }[op];
}

const text = (v: unknown) => (v == null ? null : String(v).toLowerCase());
const number = (v: unknown) => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
};
const cell = (v: unknown) =>
  v == null
    ? "—"
    : typeof v === "number"
      ? num(v)
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);

/** A select's options: as written, else the distinct values of its table's field. */
function options(c: BoardControl, tables: Record<string, Loaded | undefined>) {
  if (c.options) return c.options.map(String);
  const rows = (c.data && tables[c.data]?.rows) || [];
  const seen = new Set<string>();
  for (const r of rows) if (c.field && r[c.field] != null) seen.add(String(r[c.field]));
  return [...seen].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

function Control({
  control: c,
  id,
  value,
  options,
  onChange,
}: {
  control: BoardControl;
  id: string;
  value: Value;
  options: string[];
  onChange: (v: Value) => void;
}) {
  const label = c.label ?? c.id;
  const input = `${useId()}-input`;
  const help = c.about && <Help label={`What ${label} does`}>{c.about}</Help>;
  if (c.kind === "toggle")
    return (
      <div {...part(id)} className="flex h-8 items-center gap-2 text-sm">
        <Checkbox
          id={input}
          checked={value === true}
          onCheckedChange={(v) => onChange(v === true ? true : null)}
        />
        <label htmlFor={input} className="text-muted-foreground text-xs">
          {label}
        </label>
        {help}
      </div>
    );
  return (
    <div {...part(id)} className="flex flex-col gap-1">
      <span className="text-muted-foreground flex items-center gap-1 text-xs">
        {c.kind === "multi" ? (
          <span id={input}>{label}</span>
        ) : (
          <label htmlFor={input}>{label}</label>
        )}
        {help}
      </span>
      {c.kind === "select" && (
        <NativeSelect
          id={input}
          value={value == null ? "" : String(value)}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">All</option>
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </NativeSelect>
      )}
      {c.kind === "multi" && (
        <span className="flex flex-wrap gap-1" role="group" aria-labelledby={input}>
          {options.map((o) => {
            const on = Array.isArray(value) && value.map(String).includes(o);
            const now = Array.isArray(value) ? value.map(String) : [];
            return (
              <button
                key={o}
                type="button"
                aria-pressed={on}
                onClick={() => onChange(on ? now.filter((x) => x !== o) : [...now, o])}
                className={cn(
                  "h-8 rounded-md border px-2.5 text-sm transition-colors",
                  on ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60",
                )}
              >
                {o}
              </button>
            );
          })}
        </span>
      )}
      {c.kind === "range" && (
        <span className="flex h-8 items-center gap-2">
          <input
            type="range"
            min={c.min ?? 0}
            max={c.max ?? 1}
            step={c.step ?? "any"}
            id={input}
            value={typeof value === "number" ? value : (c.min ?? 0)}
            onChange={(e) => onChange(Number(e.target.value))}
            className="accent-foreground w-36"
          />
          <span className="w-12 text-right font-mono text-xs tabular-nums">
            {typeof value === "number" ? num(value) : "—"}
          </span>
        </span>
      )}
      {c.kind === "search" && (
        <Input
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value || null)}
          id={input}
          placeholder="Search"
          className="h-8 w-48"
        />
      )}
    </div>
  );
}

/** A panel's rows: its table's, through its filters. Worked out again only when the table or a
 * param its filters name changes, so a chart does not redraw for a param it does not use. */
function useRows(p: BoardPanel, source: Row[], params: Params): Row[] {
  const where = p.where ?? [];
  const wants = JSON.stringify(where.map((f) => (f.param ? (params[f.param] ?? null) : null)));
  return useMemo(() => {
    const values = JSON.parse(wants) as Value[];
    const fixed = where.map((f, i) => (f.param ? { ...f, param: null, value: values[i] } : f));
    return source.filter((r) => fixed.every((f) => keep(r, f as BoardFilter, {})));
    // where is the panel's own and changes with it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, p, wants]);
}

/** The params a Vega spec names, by their values: what its chart redraws for. */
function useUsed(spec: unknown, params: Params): Params {
  const text = JSON.stringify(spec ?? {});
  const used = JSON.stringify(
    Object.fromEntries(Object.entries(params).filter(([k]) => new RegExp(`\\b${k}\\b`).test(text))),
  );
  return useMemo(() => JSON.parse(used) as Params, [used]);
}

function Panel({
  panel: p,
  source,
  columns,
  edges,
  params,
  onPick,
}: {
  panel: BoardPanel;
  source: Row[];
  columns: string[];
  edges: Row[];
  params: Params;
  onPick: (value: string) => void;
}) {
  const rows = useRows(p, source, params);
  const used = useUsed(p.spec, params);
  const selected = p.select ? params[p.select.param] : null;
  switch (p.kind) {
    case "vega":
      return <VegaPanel panel={p} rows={rows} params={used} onPick={onPick} />;
    case "plotly":
      return <PlotlyPanel panel={p} rows={rows} selected={selected} onPick={onPick} />;
    case "table":
      return (
        <TablePanel panel={p} rows={rows} columns={columns} selected={selected} onPick={onPick} />
      );
    case "stat":
      return <StatPanel panel={p} rows={rows} />;
    case "text":
      return (
        <div className="text-sm">
          <Markdown noImages>
            {(p.markdown ?? "").replace(/\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g, (_, k: string) => {
              const v = params[k];
              return v == null ? "—" : Array.isArray(v) ? v.join(", ") : String(v);
            })}
          </Markdown>
        </div>
      );
    case "detail":
      return <DetailPanel rows={rows} columns={p.columns ?? columns} />;
    case "diagram":
      return (
        <DiagramPanel panel={p} nodes={rows} edges={edges} selected={selected} onPick={onPick} />
      );
  }
}

function VegaPanel({
  panel: p,
  rows,
  params,
  onPick,
}: {
  panel: BoardPanel;
  rows: Row[];
  params: Params;
  onPick: (value: string) => void;
}) {
  const view = useMemo((): VegaView => {
    const spec = p.spec ?? {};
    const own = new Set(
      ((spec.params as { name?: string }[] | undefined) ?? []).map((x) => x.name),
    );
    // the board's params as the spec's own, so a condition can test datum.model == model
    const given = Object.entries(params)
      .filter(([k]) => !own.has(k))
      .map(([k, v]) => ({ name: k, value: v }));
    return {
      kind: "vega",
      title: p.title ?? p.id,
      spec: {
        ...(p.height ? { height: p.height } : {}),
        ...spec,
        data: { values: rows },
        params: [...((spec.params as unknown[] | undefined) ?? []), ...given],
      },
      items: p.select ? { field: p.select.field } : null,
    };
  }, [p, rows, params]);
  return (
    <VegaFigure
      view={view}
      onMark={p.select ? (key, clicked) => clicked && key !== null && onPick(key) : undefined}
    />
  );
}

/** Traces from rows: one per value of color, its points' ids the select field's values. */
function traces(p: BoardPanel, rows: Row[], selected: Value) {
  const groups = new Map<string, Row[]>();
  for (const r of rows) {
    const g = p.color ? String(r[p.color] ?? "—") : "";
    groups.set(g, [...(groups.get(g) ?? []), r]);
  }
  const line = p.trace === "line";
  return [...groups].map(([g, rs]) => {
    const col = (f?: string | null) => (f ? rs.map((r) => r[f]) : undefined);
    const ids = p.select ? rs.map((r) => String(r[p.select!.field] ?? "")) : undefined;
    const chosen =
      ids && selected != null
        ? ids.flatMap((id, i) => (id === String(selected) ? [i] : []))
        : undefined;
    return Object.fromEntries(
      Object.entries({
        type: line ? "scatter" : p.trace,
        mode: line ? "lines+markers" : p.trace?.startsWith("scatter") ? "markers" : undefined,
        name: g || undefined,
        x: col(p.x),
        y: col(p.y),
        z: col(p.z),
        text: col(p.text),
        ids,
        selectedpoints: chosen,
        marker: p.size ? { size: col(p.size) } : undefined,
      }).filter(([, v]) => v !== undefined),
    );
  });
}

function PlotlyPanel({
  panel: p,
  rows,
  selected,
  onPick,
}: {
  panel: BoardPanel;
  rows: Row[];
  selected: Value;
  onPick: (value: string) => void;
}) {
  const view = useMemo((): PlotlyView => {
    const steps = p.frame ? [...new Set(rows.map((r) => String(r[p.frame!] ?? "")))] : [];
    steps.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const at = (s: string) => rows.filter((r) => String(r[p.frame!] ?? "") === s);
    const frames = steps.map((s) => ({ name: s, data: traces(p, at(s), selected) }));
    return {
      kind: "plotly",
      title: p.title ?? p.id,
      data: frames[0]?.data ?? traces(p, rows, selected),
      layout: { ...(p.height ? { height: p.height } : {}), ...(p.layout ?? {}) },
      frames: frames.length ? frames : null,
    };
  }, [p, rows, selected]);
  if (rows.length === 0) return <Empty />;
  return (
    <PlotlyFigure
      view={view}
      onMark={p.select ? (key, clicked) => clicked && key !== null && onPick(key) : undefined}
    />
  );
}

function TablePanel({
  panel: p,
  rows,
  columns,
  selected,
  onPick,
}: {
  panel: BoardPanel;
  rows: Row[];
  columns: string[];
  selected: Value;
  onPick: (value: string) => void;
}) {
  const [sort, setSort] = useState<{ field: string | null; desc: boolean }>({
    field: p.sort ?? null,
    desc: p.desc ?? false,
  });
  const [all, setAll] = useState(false);
  const cols = p.columns ?? columns;
  const sorted = useMemo(() => {
    if (!sort.field) return rows;
    const f = sort.field;
    const by = (a: Row, b: Row) => {
      const x = number(a[f]);
      const y = number(b[f]);
      if (x !== null && y !== null) return x - y;
      return String(a[f] ?? "").localeCompare(String(b[f] ?? ""), undefined, { numeric: true });
    };
    return [...rows].sort((a, b) => (sort.desc ? by(b, a) : by(a, b)));
  }, [rows, sort]);
  if (rows.length === 0) return <Empty />;
  const shown = all ? sorted : sorted.slice(0, PAGE);
  return (
    <div
      className="overflow-auto"
      style={{ maxHeight: p.height ?? 384 }}
      tabIndex={0}
      aria-label={p.title ?? p.id}
    >
      <Table>
        <TableHeader className="bg-background sticky top-0 z-10">
          <TableRow>
            {cols.map((c) => (
              <TableHead
                key={c}
                aria-sort={sort.field === c ? (sort.desc ? "descending" : "ascending") : undefined}
              >
                <button
                  type="button"
                  className="hover:text-foreground"
                  onClick={() =>
                    setSort((s) => ({ field: c, desc: s.field === c ? !s.desc : false }))
                  }
                >
                  {c}
                  {sort.field === c && (sort.desc ? " ↓" : " ↑")}
                </button>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.map((r, i) => {
            const key = p.select ? String(r[p.select.field] ?? "") : null;
            return (
              <TableRow
                key={i}
                {...(key !== null && {
                  tabIndex: 0,
                  "aria-selected": selected != null && String(selected) === key,
                  onClick: () => onPick(key),
                  onKeyDown: (e: React.KeyboardEvent) => {
                    if (e.key !== "Enter" && e.key !== " ") return;
                    e.preventDefault();
                    onPick(key);
                  },
                })}
                data-state={
                  key !== null && selected != null && String(selected) === key
                    ? "selected"
                    : undefined
                }
                className={cn(
                  key !== null &&
                    "focus-visible:ring-ring/50 cursor-pointer outline-none focus-visible:ring-[3px] focus-visible:ring-inset",
                )}
              >
                {cols.map((c) => (
                  <TableCell
                    key={c}
                    className={
                      typeof r[c] === "number"
                        ? "text-right font-mono tabular-nums"
                        : "max-w-xs truncate text-sm"
                    }
                  >
                    {cell(r[c])}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {!all && sorted.length > PAGE && (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="text-muted-foreground hover:text-foreground mt-2 text-xs"
        >
          Show all {sorted.length.toLocaleString()}
        </button>
      )}
    </div>
  );
}

function StatPanel({ panel: p, rows }: { panel: BoardPanel; rows: Row[] }) {
  const values = p.field ? rows.map((r) => number(r[p.field!])).filter((v) => v !== null) : [];
  const n = values.length;
  const value =
    p.op === "count"
      ? rows.length
      : p.op === "distinct"
        ? new Set(rows.map((r) => String(r[p.field!]))).size
        : n === 0
          ? null
          : p.op === "sum"
            ? values.reduce((a, b) => a + b, 0)
            : p.op === "mean"
              ? values.reduce((a, b) => a + b, 0) / n
              : p.op === "min"
                ? Math.min(...values)
                : Math.max(...values);
  return (
    <p className="font-mono text-2xl tabular-nums">
      {p.format === "percent" ? pct(value) : num(value)}
    </p>
  );
}

function DetailPanel({ rows, columns }: { rows: Row[]; columns: string[] }) {
  const row = rows[0];
  if (!row) return <p className="text-muted-foreground text-sm">Pick one in another panel.</p>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {columns
        .filter((c) => c in row)
        .map((c) => (
          <div key={c} className="contents">
            <dt className="text-muted-foreground">{c}</dt>
            <dd
              className={cn(
                "min-w-0 break-words whitespace-pre-wrap",
                typeof row[c] === "number" && "font-mono tabular-nums",
              )}
            >
              {cell(row[c])}
            </dd>
          </div>
        ))}
    </dl>
  );
}

const Empty = () => <p className="text-muted-foreground text-sm">No rows pass the filters.</p>;

/** Nodes and edges laid out by dagre, drawn as SVG in the app's colours. A node's shade is its
 * color field's value; the picked node is outlined. */
function DiagramPanel({
  panel: p,
  nodes,
  edges,
  selected,
  onPick,
}: {
  panel: BoardPanel;
  nodes: Row[];
  edges: Row[];
  selected: Value;
  onPick: (value: string) => void;
}) {
  const [layout, setLayout] = useState<Layout | null>(null);
  // an id for the arrowhead unique on the page, so two diagrams do not share one
  const marker = `arrow${useId().replace(/:/g, "")}`;
  useEffect(() => {
    let done = false;
    void lay(p, nodes, edges).then((l) => !done && setLayout(l));
    return () => {
      done = true;
    };
  }, [p, nodes, edges]);
  if (nodes.length === 0) return <Empty />;
  if (!layout) return <Skeleton className="h-40 w-full" />;
  const shades = [...new Set(nodes.map((n) => (p.color ? String(n[p.color] ?? "") : "")))];
  const shade = (n: Row) => {
    const i = shades.indexOf(p.color ? String(n[p.color] ?? "") : "");
    return `color-mix(in oklch, var(--foreground) ${shades.length > 1 ? 6 + (i * 24) / (shades.length - 1) : 8}%, var(--background))`;
  };
  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      className="mx-auto w-full"
      style={{ maxHeight: p.height ?? 420, maxWidth: layout.width }}
      role={p.select ? "group" : "img"}
      aria-label={p.title ?? p.id}
    >
      <defs>
        <marker
          id={marker}
          viewBox="0 0 10 10"
          refX="10"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted-foreground)" />
        </marker>
      </defs>
      {layout.edges.map((e, i) => (
        <polyline
          key={i}
          points={e.points.map((pt) => `${pt.x},${pt.y}`).join(" ")}
          fill="none"
          stroke="var(--muted-foreground)"
          strokeWidth={1}
          markerEnd={`url(#${marker})`}
        />
      ))}
      {layout.nodes.map((n) => {
        const id = String(n.row[p.node!] ?? "");
        const pick = p.select ? String(n.row[p.select.field] ?? "") : null;
        const on = pick !== null && selected != null && String(selected) === pick;
        return (
          <g
            key={id}
            transform={`translate(${n.x - n.width / 2},${n.y - n.height / 2})`}
            {...(pick !== null && {
              role: "button",
              tabIndex: 0,
              "aria-pressed": on,
              "aria-label": n.text,
              onClick: () => onPick(pick),
              onKeyDown: (e: React.KeyboardEvent) => {
                if (e.key !== "Enter" && e.key !== " ") return;
                e.preventDefault();
                onPick(pick);
              },
            })}
            className={cn(
              pick !== null &&
                "cursor-pointer outline-none [&:focus-visible>rect]:stroke-[var(--ring)]",
            )}
          >
            <title>{id}</title>
            <rect
              width={n.width}
              height={n.height}
              rx={6}
              fill={shade(n.row)}
              stroke={on ? "var(--foreground)" : "var(--border)"}
              strokeWidth={on ? 2 : 1}
            />
            <text
              x={n.width / 2}
              y={n.height / 2}
              dominantBaseline="central"
              textAnchor="middle"
              fontSize={12}
              fill="var(--foreground)"
            >
              {n.text}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

type Layout = {
  width: number;
  height: number;
  nodes: { row: Row; text: string; x: number; y: number; width: number; height: number }[];
  edges: { points: { x: number; y: number }[] }[];
};

/** dagre's layered layout; loaded only when a board has a diagram. Edges to a node the filters
 * left out are left out. */
async function lay(p: BoardPanel, nodes: Row[], edges: Row[]): Promise<Layout> {
  const { graphlib, layout } = await import("@dagrejs/dagre");
  const g = new graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: p.direction ?? "LR", nodesep: 24, ranksep: 48, marginx: 8, marginy: 8 });
  g.setDefaultEdgeLabel(() => ({}));
  const byId = new Map<string, Row>();
  for (const n of nodes) {
    const id = String(n[p.node!] ?? "");
    const text = String(n[p.label ?? p.node!] ?? id);
    byId.set(id, n);
    g.setNode(id, { width: Math.min(240, 24 + text.length * 7), height: 32, text });
  }
  edges.forEach((e, i) => {
    const s = String(e[p.source!] ?? "");
    const t = String(e[p.target!] ?? "");
    if (byId.has(s) && byId.has(t)) g.setEdge(s, t, {}, String(i));
  });
  layout(g);
  const graph = g.graph();
  return {
    width: Math.max(1, graph.width ?? 1),
    height: Math.max(1, graph.height ?? 1),
    nodes: g.nodes().map((id) => {
      const n = g.node(id) as unknown as {
        x: number;
        y: number;
        width: number;
        height: number;
        text: string;
      };
      return { row: byId.get(id)!, text: n.text, x: n.x, y: n.y, width: n.width, height: n.height };
    }),
    edges: g.edges().map((e) => ({
      points: (g.edge(e) as unknown as { points: { x: number; y: number }[] }).points,
    })),
  };
}
