"use client";

import { useQueries } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Help } from "@/components/help";
import { Term } from "@/components/term";
import { ScoreCell } from "@/components/metric";
import { RecordFields, RecordsTable } from "@/components/record-view";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { RunDetail } from "@/lib/api";
import {
  artifactQuery,
  asBinary,
  brief,
  defaultField,
  downloadJsonl,
  itemFolders,
  joinKey,
  parseJsonl,
  sharedFields,
  splitBy,
  splitColumns,
  stem,
  textField,
  traceShape,
  wilson,
  type Row,
} from "@/lib/artifacts";
import { cn } from "@/lib/utils";

/** Whether a run has per-item files to line up: a folder of two or more JSONL files. */
export function hasItems(run: RunDetail): boolean {
  return itemFolders(run.artifacts.map((a) => a.path)).length > 0;
}

/** A run's per-item records, one row per item and one column per condition (a JSONL file in the
 * same folder), each read against the reference condition. */
export function ItemsView({ run }: { run: RunDetail }) {
  const folders = useMemo(() => itemFolders(run.artifacts.map((a) => a.path)), [run.artifacts]);
  const [set, setSet] = useQueryState("set", parseAsString);
  const folder = folders.find((f) => f.dir === set) ?? folders[0];
  if (!folder) return <p className="text-muted-foreground text-sm">No per-item files.</p>;
  return (
    <div className="flex flex-col gap-4">
      {folders.length > 1 && (
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Records</span>
          <NativeSelect value={folder.dir} onChange={(e) => void setSet(e.target.value)}>
            {folders.map((f) => (
              <option key={f.dir} value={f.dir}>
                {f.dir || "(top level)"} · {f.files.length} files
              </option>
            ))}
          </NativeSelect>
        </label>
      )}
      <Folder key={folder.dir} runId={run.id} files={folder.files} />
    </div>
  );
}

function Folder({ runId, files }: { runId: string; files: string[] }) {
  const queries = useQueries({ queries: files.map((f) => artifactQuery(runId, f)) });
  const failed = queries.find((q) => q.error);
  if (failed) return <p className="text-negative text-sm">{String(failed.error)}</p>;
  if (queries.some((q) => q.data === undefined)) return <Skeleton className="h-64 w-full" />;
  const tables = queries.map((q) => parseJsonl(q.data!).rows);
  // a folder of traces (one request a file) is not conditions over the same items
  if (tables.every((t) => traceShape(t) !== null)) {
    const dir = files[0].includes("/") ? files[0].slice(0, files[0].lastIndexOf("/")) : "";
    return (
      <p className="text-muted-foreground text-sm">
        These files are traces, one request each, not conditions over the same items.{" "}
        <Link
          href={`?id=${encodeURIComponent(runId)}&tab=artifacts&file=${encodeURIComponent(`${dir}/*`)}`}
          className="text-foreground underline underline-offset-4"
        >
          Read them as timelines
        </Link>
        .
      </p>
    );
  }
  return <Aligned files={files} tables={tables} />;
}

type Transition = { down: number; up: number; wasOne: number; wasZero: number };

/** One file's records, as a table or, split by a column (an arm, a condition), lined up item by
 * item across its values as the Items tab lines up a folder of files. */
export function LinedUp({ rows, name }: { rows: Row[]; name: string }) {
  const columns = useMemo(() => splitColumns(rows), [rows]);
  const [by, setBy] = useQueryState("by", parseAsString);
  const split = by && columns.includes(by) ? splitBy(rows, by) : null;
  return (
    <div className="flex flex-col gap-3">
      {columns.length > 0 && (
        <label className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Line up by</span>
          <NativeSelect
            value={split ? by! : ""}
            onChange={(e) => void setBy(e.target.value || null)}
            className="font-mono text-xs"
          >
            <option value="">none: every row</option>
            {columns.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </NativeSelect>
        </label>
      )}
      {split ? (
        <Aligned files={split.names} tables={split.tables} />
      ) : (
        <RecordsTable rows={rows} name={name} />
      )}
    </div>
  );
}

function Aligned({ files, tables }: { files: string[]; tables: Row[][] }) {
  const names = files.map(stem);
  const key = useMemo(() => joinKey(tables), [tables]);
  const fields = useMemo(() => (key ? sharedFields(tables, key) : []), [tables, key]);
  const [fieldParam, setField] = useQueryState("field", parseAsString);
  const [refParam, setRef] = useQueryState("ref", parseAsString);
  const [show, setShow] = useQueryState("show", parseAsString);
  const [item, setItem] = useQueryState("item", parseAsString);
  const [search, setSearch] = useState("");

  // a field with one value per file (the condition's own name) differs by construction
  const constant = useMemo(
    () =>
      new Set(
        Object.keys(tables[0]?.[0] ?? {}).filter((f) =>
          tables.every((t) => new Set(t.map((r) => JSON.stringify(r[f]))).size === 1),
        ),
      ),
    [tables],
  );
  const field =
    fieldParam && fields.includes(fieldParam) ? fieldParam : defaultField(tables, fields);
  const ref = refParam && names.includes(refParam) ? names.indexOf(refParam) : 0;

  const items = useMemo(() => {
    if (!key) return [];
    const byKey = tables.map((t) => new Map(t.map((r) => [String(r[key]), r])));
    const order = [...new Set(tables.flatMap((t) => t.map((r) => String(r[key]))))];
    return order.map((id) => ({ id, rows: byKey.map((m) => m.get(id)) }));
  }, [tables, key]);

  if (!key || !field)
    return (
      <p className="text-muted-foreground text-sm">
        These files ({names.join(", ")}) share no field that names an item once in every file, so
        they cannot be lined up. Each one is under Artifacts.
      </p>
    );

  const binary = items.every((it) => it.rows.every((r) => !r || asBinary(r[field]) !== null));
  const text = textField(tables[ref], key);
  const differs = (it: (typeof items)[number], i: number) =>
    i !== ref &&
    it.rows[i] !== undefined &&
    it.rows[ref] !== undefined &&
    JSON.stringify(it.rows[i]![field]) !== JSON.stringify(it.rows[ref]![field]);

  // per condition against the reference: how many items changed, and for a 0/1 field which way
  const stats = names.map((_, i) => {
    let both = 0;
    let changed = 0;
    let k = 0;
    let n = 0;
    const t: Transition = { down: 0, up: 0, wasOne: 0, wasZero: 0 };
    for (const it of items) {
      const r = it.rows[i];
      if (!r) continue;
      const b = asBinary(r[field]);
      if (b !== null) {
        n += 1;
        k += b;
      }
      const base = it.rows[ref];
      if (!base || i === ref) continue;
      both += 1;
      if (differs(it, i)) changed += 1;
      const before = asBinary(base[field]);
      if (before === 1) {
        t.wasOne += 1;
        if (b === 0) t.down += 1;
      } else if (before === 0) {
        t.wasZero += 1;
        if (b === 1) t.up += 1;
      }
    }
    return { both, changed, k, n, t };
  });

  const needle = search.toLowerCase();
  const shown = items.filter((it) => {
    if (
      needle &&
      !JSON.stringify(it.rows).toLowerCase().includes(needle) &&
      !it.id.toLowerCase().includes(needle)
    )
      return false;
    if (!show) return true;
    if (show === "changed") return names.some((_, i) => differs(it, i));
    const [kind, cond] = show.split(":");
    const i = names.indexOf(cond);
    if (i < 0) return true;
    const before = asBinary(it.rows[ref]?.[field]);
    const after = asBinary(it.rows[i]?.[field]);
    if (kind === "changed") return differs(it, i);
    if (kind === "down") return before === 1 && after === 0;
    if (kind === "up") return before === 0 && after === 1;
    return true;
  });
  const opened = items.find((it) => it.id === item);

  return (
    <div className="flex flex-col gap-4">
      <Summary names={names} ref_={ref} field={field} binary={binary} stats={stats} />
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search items…"
          aria-label="Search items"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <label className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Compare on</span>
          <NativeSelect
            value={field}
            onChange={(e) => void setField(e.target.value)}
            className="font-mono text-xs"
          >
            {fields.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">against</span>
          <NativeSelect
            value={names[ref]}
            onChange={(e) => void setRef(e.target.value)}
            className="font-mono text-xs"
          >
            {names.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Show</span>
          <NativeSelect
            value={show ?? ""}
            onChange={(e) => void setShow(e.target.value || null)}
            className="text-xs"
          >
            <option value="">every item</option>
            <option value="changed">changed in any condition</option>
            {names.map((n, i) =>
              i === ref ? null : binary ? (
                <optgroup key={n} label={n}>
                  <option value={`changed:${n}`}>changed in {n}</option>
                  <option value={`down:${n}`}>1 → 0 in {n}</option>
                  <option value={`up:${n}`}>0 → 1 in {n}</option>
                </optgroup>
              ) : (
                <option key={n} value={`changed:${n}`}>
                  changed in {n}
                </option>
              ),
            )}
          </NativeSelect>
        </label>
        <span className="text-muted-foreground ml-auto font-mono text-xs">
          {shown.length} of {items.length} items
        </span>
        <Button
          variant="outline"
          size="sm"
          title="Download the items shown, each with its record in every condition, as JSONL"
          onClick={() =>
            downloadJsonl(
              shown.map((it) => ({
                [key]: it.rows.find(Boolean)?.[key] ?? it.id,
                ...Object.fromEntries(names.map((n, i) => [n, it.rows[i] ?? null])),
              })),
              "items.shown.jsonl",
            )
          }
        >
          <Download /> Items
        </Button>
      </div>
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-16 font-mono text-xs">{key}</TableHead>
              {text && (
                <TableHead className="hidden font-mono text-xs sm:table-cell">{text}</TableHead>
              )}
              {names.map((n, i) => (
                <TableHead key={n} className="text-right font-mono text-xs whitespace-nowrap">
                  {n}
                  {i === ref && <span className="text-muted-foreground"> · ref</span>}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((it) => (
              <TableRow
                key={it.id}
                className="focus-visible:ring-ring/50 cursor-pointer outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
                data-state={item === it.id ? "selected" : undefined}
                tabIndex={0}
                onClick={() => void setItem(it.id)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter" && e.key !== " ") return;
                  e.preventDefault();
                  void setItem(it.id);
                }}
              >
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {it.id}
                  {text && (
                    <span className="text-foreground mt-1 line-clamp-2 block font-sans text-sm whitespace-normal sm:hidden">
                      {brief(it.rows[ref]?.[text], 140)}
                    </span>
                  )}
                </TableCell>
                {text && (
                  <TableCell className="hidden max-w-md truncate text-sm sm:table-cell">
                    {brief(it.rows[ref]?.[text], 140)}
                  </TableCell>
                )}
                {names.map((n, i) => (
                  <TableCell key={n} className="text-right">
                    <Cell
                      value={it.rows[i]?.[field]}
                      missing={!it.rows[i]}
                      binary={binary}
                      changed={differs(it, i)}
                    />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Sheet open={!!opened} onOpenChange={(o) => !o && void setItem(null)}>
        <SheetContent className="sm:max-w-6xl">
          {opened && (
            <ItemDetail
              id={opened.id}
              keyName={key}
              names={names}
              rows={opened.rows}
              ref_={ref}
              constant={constant}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function Cell({
  value,
  missing,
  binary,
  changed,
}: {
  value: unknown;
  missing: boolean;
  binary: boolean;
  changed: boolean;
}) {
  if (missing) return <span className="text-muted-foreground font-mono text-xs">—</span>;
  const b = binary ? asBinary(value) : null;
  return (
    <span
      className={cn(
        "inline-flex min-w-7 justify-end rounded px-1.5 py-0.5",
        changed &&
          (b === 0 ? "bg-negative/10" : b === 1 ? "bg-positive/10" : "bg-muted font-medium"),
      )}
      title={changed ? "differs from the reference" : undefined}
    >
      {b !== null ? (
        <ScoreCell value={b} />
      ) : (
        <span className="font-mono text-xs">{brief(value, 30)}</span>
      )}
    </span>
  );
}

function Summary({
  names,
  ref_,
  field,
  binary,
  stats,
}: {
  names: string[];
  ref_: number;
  field: string;
  binary: boolean;
  stats: { both: number; changed: number; k: number; n: number; t: Transition }[];
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium">
        By condition
        {binary ? (
          <span className="text-muted-foreground flex items-center gap-3 text-xs font-normal">
            <Term k="wilson">rate, 95% interval</Term>
            <Term k="transition">1→0 · 0→1</Term>
          </span>
        ) : (
          <Help>{`How many items have a different ${field} from the reference, out of the items both files hold.`}</Help>
        )}
      </div>
      <div className="grid overflow-hidden rounded-xl border sm:grid-cols-2 lg:grid-cols-4 [&>*]:-mr-px [&>*]:-mb-px [&>*]:border-r [&>*]:border-b">
        {names.map((n, i) => {
          const s = stats[i];
          const ci = binary ? wilson(s.k, s.n) : null;
          return (
            <div key={n} className="flex flex-col gap-1 p-4">
              <span className="text-muted-foreground font-mono text-xs">
                {n}
                {i === ref_ && " · reference"}
              </span>
              {binary ? (
                <>
                  <span className="font-mono text-2xl font-medium tabular-nums">
                    {s.n ? `${((s.k / s.n) * 100).toFixed(1)}%` : "—"}
                  </span>
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {s.k}/{s.n}
                    {ci && ` · ${(ci[0] * 100).toFixed(0)}–${(ci[1] * 100).toFixed(0)}%`}
                  </span>
                  {i !== ref_ && (
                    <span className="font-mono text-xs tabular-nums">
                      <span className="text-negative">
                        1→0 {s.t.down}/{s.t.wasOne}
                      </span>
                      {" · "}
                      <span className="text-positive">
                        0→1 {s.t.up}/{s.t.wasZero}
                      </span>
                    </span>
                  )}
                </>
              ) : (
                <span className="font-mono text-2xl font-medium tabular-nums">
                  {i === ref_ ? "—" : `${s.changed}/${s.both}`}
                </span>
              )}
              {i !== ref_ && !binary && (
                <span className="text-muted-foreground text-xs">changed from the reference</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** One item in every condition side by side; fields that differ from the reference outlined. */
function ItemDetail({
  id,
  keyName,
  names,
  rows,
  ref_,
  constant,
}: {
  id: string;
  keyName: string;
  names: string[];
  rows: (Row | undefined)[];
  ref_: number;
  constant: Set<string>;
}) {
  const base = rows[ref_];
  return (
    <>
      <div className="border-b px-6 py-4 pr-12">
        <SheetTitle className="font-semibold">
          <span className="text-muted-foreground font-mono text-sm">{keyName}</span> {id}
        </SheetTitle>
        <SheetDescription className="text-muted-foreground text-xs">
          Every condition&apos;s record for this item; fields that differ from {names[ref_]} are
          outlined.
        </SheetDescription>
      </div>
      <div className="flex-1 overflow-auto px-6 py-5">
        <div
          className="grid gap-6"
          style={{ gridTemplateColumns: `repeat(auto-fit, minmax(16rem, 1fr))` }}
        >
          {names.map((n, i) => {
            const r = rows[i];
            const changed = new Set(
              r && base && i !== ref_
                ? Object.keys(r).filter(
                    (k) => !constant.has(k) && JSON.stringify(r[k]) !== JSON.stringify(base[k]),
                  )
                : [],
            );
            return (
              <section key={n} className="flex min-w-0 flex-col gap-3">
                <h3 className="border-b pb-1 font-mono text-sm font-medium">
                  {n}
                  {i === ref_ && <span className="text-muted-foreground"> · reference</span>}
                </h3>
                {r ? (
                  <RecordFields row={r} changed={changed} />
                ) : (
                  <p className="text-muted-foreground text-sm">Not in this file.</p>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </>
  );
}
