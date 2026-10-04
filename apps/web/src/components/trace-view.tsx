"use client";

import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { Help } from "@/components/help";
import { RecordFields } from "@/components/record-view";
import { brief, isScalar, moment, type Row } from "@/lib/artifacts";
import { cn } from "@/lib/utils";

/** Fields a summary line leaves out: the ones the timeline already shows, and bulky ids. */
const QUIET =
  /(^|_)(ids?|tenant_id|user_id|conversation_id|request_id|trace_id|span_id)$|^source_file$/;

/** A trace's events, one timeline per request: when each happened from the request's start, how
 * long it took when it says (duration_ms), its kind and a line of what it carried; an event opens
 * to every field. Many requests are listed newest first, each folding. */
export function Timeline({
  rows,
  time,
  kind,
  group,
}: {
  rows: Row[];
  time: string;
  kind: string;
  group: string | null;
}) {
  const groups = useMemo(() => {
    const by = new Map<string, Row[]>();
    for (const r of rows) {
      const g = group ? String(r[group]) : "trace";
      by.set(g, [...(by.get(g) ?? []), r]);
    }
    return [...by]
      .map(([id, events]) => {
        const sorted = [...events].sort((a, b) => moment(a[time])! - moment(b[time])!);
        const start = moment(sorted[0][time])!;
        const end = Math.max(...sorted.map((e) => moment(e[time])! + (Number(e.duration_ms) || 0)));
        return { id, events: sorted, start, span: Math.max(1, end - start) };
      })
      .sort((a, b) => b.start - a.start);
  }, [rows, time, group]);
  const kinds = useMemo(() => [...new Set(rows.map((r) => String(r[kind])))], [rows, kind]);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
        {groups.length} {groups.length === 1 ? "trace" : "traces"} · {rows.length} events ·{" "}
        {kinds.length} kinds
        <Help>
          {`Events read as a trace: ordered by ${time}, named by ${kind}${group ? `, one timeline per ${group}` : ""}. Offsets are from the trace's first event; a bar is the event's own duration_ms, against the whole trace.`}
        </Help>
      </p>
      {groups.slice(0, 50).map((g, i) => (
        <Trace key={g.id} trace={g} time={time} kind={kind} open={i === 0} />
      ))}
      {groups.length > 50 && (
        <p className="text-muted-foreground text-xs">
          The newest 50 of {groups.length} traces shown.
        </p>
      )}
    </div>
  );
}

function Trace({
  trace,
  time,
  kind,
  open,
}: {
  trace: { id: string; events: Row[]; start: number; span: number };
  time: string;
  kind: string;
  open: boolean;
}) {
  const [shown, setShown] = useState<number | null>(null);
  return (
    <details open={open} className="group rounded-xl border">
      <summary className="hover:bg-accent/40 flex cursor-pointer items-center gap-3 px-4 py-2.5 text-sm select-none">
        <ChevronRight className="text-muted-foreground size-4 shrink-0 transition-transform group-open:rotate-90" />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">{trace.id}</span>
        <span className="text-muted-foreground font-mono text-xs tabular-nums">
          {trace.events.length} events · {ms(trace.span)}
        </span>
        <span className="text-muted-foreground hidden text-xs sm:inline">
          {new Date(trace.start).toLocaleString()}
        </span>
      </summary>
      <ol className="divide-y border-t">
        {trace.events.map((e, i) => {
          const offset = moment(e[time])! - trace.start;
          const duration = Number(e.duration_ms) || 0;
          return (
            <li key={i}>
              <button
                type="button"
                onClick={() => setShown(shown === i ? null : i)}
                aria-expanded={shown === i}
                className="hover:bg-accent/40 grid w-full grid-cols-[4.5rem_minmax(0,9rem)_minmax(0,1fr)] items-center gap-3 px-4 py-2 text-left sm:grid-cols-[4.5rem_minmax(0,11rem)_6rem_minmax(0,1fr)]"
              >
                <span className="text-muted-foreground text-right font-mono text-xs tabular-nums">
                  +{ms(offset)}
                </span>
                <span className="truncate font-mono text-xs">{String(e[kind])}</span>
                <span
                  className="bg-muted relative hidden h-1.5 rounded-sm sm:block"
                  title={duration ? `${duration} ms` : undefined}
                >
                  <span
                    className={cn(
                      "bg-foreground/70 absolute h-1.5 rounded-sm",
                      !duration && "bg-foreground/30",
                    )}
                    style={{
                      left: `${(offset / trace.span) * 100}%`,
                      width: duration ? `${Math.max(2, (duration / trace.span) * 100)}%` : "2px",
                    }}
                  />
                </span>
                <span className="text-muted-foreground truncate text-xs">
                  {summary(e, time, kind)}
                </span>
              </button>
              {shown === i && (
                <div className="bg-muted/30 px-4 py-3">
                  <RecordFields row={e} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </details>
  );
}

function ms(v: number): string {
  if (v < 1000) return `${Math.round(v)} ms`;
  if (v < 60_000) return `${(v / 1000).toFixed(v < 10_000 ? 2 : 1)} s`;
  return `${Math.floor(v / 60_000)} m ${Math.round((v % 60_000) / 1000)} s`;
}

/** What an event carried, in a line: its scalar fields other than time and kind, then its lists'
 * lengths, quiet ids left out. */
function summary(e: Row, time: string, kind: string): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(e)) {
    if (k === time || k === kind || QUIET.test(k) || v === null || v === "") continue;
    if (isScalar(v)) parts.push(`${k}: ${brief(v, 60)}`);
    else if (Array.isArray(v)) parts.push(`${k}: ${v.length}`);
    else parts.push(`${k}: ${brief(v, 60)}`);
  }
  return parts.join(" · ");
}
