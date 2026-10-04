"use client";

import { ArrowDown, ArrowUp, Download } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { asBinary, brief, downloadJsonl, isScalar, type Row } from "@/lib/artifacts";
import { cn } from "@/lib/utils";

/** Any JSON value as a tree: objects and arrays fold, the first levels open. */
export function JsonTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (isScalar(value)) return <Scalar value={value} />;
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value as object);
  const open = Array.isArray(value) ? "[" : "{";
  const close = Array.isArray(value) ? "]" : "}";
  if (entries.length === 0) return <span className="font-mono text-xs">{open + close}</span>;
  return (
    <details open={depth < 2} className="font-mono text-xs">
      <summary className="text-muted-foreground cursor-pointer select-none">
        {open} {entries.length} {Array.isArray(value) ? "items" : "fields"} {close}
      </summary>
      <div className="border-border ml-3 border-l pl-3">
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-2 py-0.5">
            <span className="text-muted-foreground shrink-0">{k}:</span>
            <div className="min-w-0 break-words">
              <JsonTree value={v} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function Scalar({ value }: { value: string | number | boolean | null }) {
  if (typeof value === "string")
    return <span className="break-words whitespace-pre-wrap">&quot;{value}&quot;</span>;
  return <span className="tabular-nums">{String(value)}</span>;
}

/** One record, field by field: text as a block, a list of numbers as bars with its largest
 * marked, anything nested as a tree. `changed` fields are outlined. */
export function RecordFields({ row, changed }: { row: Row; changed?: Set<string> }) {
  return (
    <dl className="flex flex-col gap-3">
      {Object.entries(row).map(([k, v]) => (
        <div
          key={k}
          className={cn(
            "flex flex-col gap-1",
            changed?.has(k) && "border-foreground/40 rounded-md border border-dashed p-2",
          )}
        >
          <dt className="text-muted-foreground font-mono text-xs">{k}</dt>
          <dd className="min-w-0">
            <FieldValue value={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function FieldValue({ value }: { value: unknown }) {
  if (typeof value === "string") {
    if (value.length > 60 || value.includes("\n"))
      return (
        <p className="bg-muted/50 rounded-md p-3 text-sm leading-relaxed break-words whitespace-pre-wrap">
          {value}
        </p>
      );
    return <span className="text-sm break-words">{value || "—"}</span>;
  }
  if (Array.isArray(value) && value.length > 1 && value.every((x) => typeof x === "number"))
    return <NumberBars values={value as number[]} />;
  if (isScalar(value)) {
    const b = typeof value === "boolean" ? asBinary(value) : null;
    return (
      <span className={cn("font-mono text-sm tabular-nums", b === 1 && "text-positive")}>
        {String(value)}
      </span>
    );
  }
  return <JsonTree value={value} depth={1} />;
}

/** A short list of numbers (option scores, logits) as bars, the largest marked. */
function NumberBars({ values }: { values: number[] }) {
  const max = Math.max(...values);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const top = values.indexOf(max);
  const sorted = [...values].sort((a, b) => b - a);
  const margin = sorted.length > 1 ? sorted[0] - sorted[1] : null;
  if (values.length > 40) return <JsonTree value={values} depth={1} />;
  return (
    <div className="flex flex-col gap-1">
      {values.map((v, i) => (
        <div key={i} className="grid grid-cols-[1.5rem_minmax(0,1fr)_5rem] items-center gap-2">
          <span className="text-muted-foreground text-right font-mono text-xs">{i}</span>
          <div className="bg-muted h-2 rounded-sm">
            <div
              className={cn("h-2 rounded-sm", i === top ? "bg-foreground" : "bg-foreground/30")}
              style={{ width: `${Math.max(2, ((v - min) / span) * 100)}%` }}
            />
          </div>
          <span className="text-right font-mono text-xs tabular-nums">{v.toFixed(3)}</span>
        </div>
      ))}
      {margin !== null && (
        <span className="text-muted-foreground font-mono text-xs">
          top {top} · margin over the next {margin.toFixed(3)}
        </span>
      )}
    </div>
  );
}

/** Columns with few values (a condition, a pass flag) become filters; past this many they do not. */
const FACET_MAX = 6;

/** Records as a table: search over every field, sort by a column, filter by a column with few
 * values, keep what is shown as JSONL; a row opens the whole record. */
export function RecordsTable({ rows, name }: { rows: Row[]; name: string }) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ col: string; desc: boolean } | null>(null);
  const [facets, setFacets] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<number | null>(null);

  const columns = useMemo(() => {
    const seen = new Set<string>();
    for (const r of rows.slice(0, 200)) for (const k of Object.keys(r)) seen.add(k);
    return [...seen];
  }, [rows]);
  const facetable = useMemo(
    () =>
      columns
        .map((c) => {
          const values = new Set(rows.map((r) => (isScalar(r[c]) ? String(r[c]) : "\u0000")));
          return [c, [...values].sort()] as const;
        })
        .filter(([, vs]) => vs.length >= 2 && vs.length <= FACET_MAX && !vs.includes("\u0000")),
    [columns, rows],
  );

  const shown = useMemo(() => {
    const needle = search.toLowerCase();
    const kept = rows
      .map((r, i) => [r, i] as const)
      .filter(
        ([r]) =>
          Object.entries(facets).every(([c, v]) => String(r[c]) === v) &&
          (!needle || JSON.stringify(r).toLowerCase().includes(needle)),
      );
    if (sort) {
      const { col, desc } = sort;
      kept.sort(([a], [b]) => {
        const x = a[col];
        const y = b[col];
        const c =
          typeof x === "number" && typeof y === "number"
            ? x - y
            : String(x ?? "").localeCompare(String(y ?? ""), undefined, { numeric: true });
        return desc ? -c : c;
      });
    }
    return kept;
  }, [rows, search, facets, sort]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search every field…"
          aria-label="Search rows"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        {facetable.map(([c, values]) => (
          <label key={c} className="flex items-center gap-1.5 text-xs">
            <span className="text-muted-foreground font-mono">{c}</span>
            <NativeSelect
              value={facets[c] ?? ""}
              onChange={(e) =>
                setFacets((f) => {
                  const next = { ...f };
                  if (e.target.value) next[c] = e.target.value;
                  else delete next[c];
                  return next;
                })
              }
              className="font-mono text-xs"
            >
              <option value="">all</option>
              {values.map((v) => (
                <option key={v} value={v}>
                  {v} ({rows.filter((r) => String(r[c]) === v).length})
                </option>
              ))}
            </NativeSelect>
          </label>
        ))}
        <span className="text-muted-foreground ml-auto font-mono text-xs">
          {shown.length} of {rows.length}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            downloadJsonl(
              shown.map(([r]) => r),
              name.replace(/\.\w+$/, "") + ".shown.jsonl",
            )
          }
          title="Download the rows shown, as JSONL"
        >
          <Download /> Rows
        </Button>
      </div>
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {columns.map((c) => (
                <TableHead
                  key={c}
                  className="whitespace-nowrap"
                  aria-sort={sort?.col !== c ? "none" : sort.desc ? "descending" : "ascending"}
                >
                  <button
                    className="hover:text-foreground inline-flex items-center gap-1 font-mono text-xs"
                    onClick={() =>
                      setSort((s) =>
                        s?.col !== c
                          ? { col: c, desc: false }
                          : s.desc
                            ? null
                            : { col: c, desc: true },
                      )
                    }
                  >
                    {c}
                    {sort?.col === c &&
                      (sort.desc ? (
                        <ArrowDown className="size-3" />
                      ) : (
                        <ArrowUp className="size-3" />
                      ))}
                  </button>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.slice(0, 500).map(([r, i]) => (
              <TableRow
                key={i}
                className="focus-visible:ring-ring/50 cursor-pointer outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
                data-state={open === i ? "selected" : undefined}
                tabIndex={0}
                onClick={() => setOpen(i)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter" && e.key !== " ") return;
                  e.preventDefault();
                  setOpen(i);
                }}
              >
                {columns.map((c) => (
                  <TableCell
                    key={c}
                    className={cn(
                      "max-w-72 truncate text-xs",
                      typeof r[c] === "number" ? "text-right font-mono tabular-nums" : "",
                      typeof r[c] !== "string" && "font-mono",
                    )}
                  >
                    {brief(r[c], 80)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {shown.length > 500 && (
        <p className="text-muted-foreground text-xs">
          The first 500 of {shown.length} shown; search or filter to narrow them.
        </p>
      )}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent>
          {open !== null && (
            <>
              <div className="border-b px-6 py-4 pr-12">
                <SheetTitle className="font-semibold">
                  {name} · row {open + 1}
                </SheetTitle>
                <SheetDescription className="sr-only">Every field of the record</SheetDescription>
              </div>
              <div className="flex-1 overflow-y-auto px-6 py-5">
                <RecordFields row={rows[open]} />
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
