"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { parseAsBoolean, parseAsString, useQueryState } from "nuqs";
import { useMemo } from "react";

import { EmptyState } from "@/components/empty-state";
import { Delta, MetricValue, ScoreCell } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { runHref } from "@/components/runs-table";
import { Transcript } from "@/components/transcript";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { q, type RunDetail, type SampleSummary } from "@/lib/api";
import { headline, metricLabel, num, stderr } from "@/lib/format";
import { cn } from "@/lib/utils";

export function CompareView() {
  const [a] = useQueryState("a", parseAsString);
  const [b] = useQueryState("b", parseAsString);
  if (!a || !b) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={GitCompareArrows}
          title="Pick two runs to compare"
          body="On Runs, tick two rows and press Compare. Metrics, flipped samples and transcripts line up here."
          command="open Runs, tick two rows, press Compare"
        />
      </section>
    );
  }
  return <Loaded a={a} b={b} />;
}

function Loaded({ a, b }: { a: string; b: string }) {
  const [ra, rb] = useQueries({ queries: [q.run(a), q.run(b)] });
  const pending = ra.isError || !ra.data ? ra : rb;
  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-8">
      {ra.data && rb.data ? (
        <>
          <Heads a={ra.data} b={rb.data} />
          <Metrics a={ra.data} b={rb.data} />
          {ra.data.kind === "eval" && rb.data.kind === "eval" && (
            <>
              <Paired a={a} b={b} />
              <Samples a={ra.data} b={rb.data} />
            </>
          )}
        </>
      ) : (
        <QueryState query={pending}>{() => null}</QueryState>
      )}
    </section>
  );
}

function Heads({ a, b }: { a: RunDetail; b: RunDetail }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {[
        ["A", a],
        ["B", b],
      ].map(([label, run]) => {
        const r = run as RunDetail;
        return (
          <Link
            key={label as string}
            href={runHref(r.id)}
            className="hover:bg-accent/40 flex items-center gap-3 rounded-xl border p-4 transition-colors"
          >
            <span className="grid size-7 place-items-center rounded-md border font-mono text-xs">
              {label as string}
            </span>
            <div className="min-w-0">
              <div className="truncate font-medium">{r.name}</div>
              <div className="text-muted-foreground truncate font-mono text-xs">{r.model}</div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function Metrics({ a, b }: { a: RunDetail; b: RunDetail }) {
  const keys = [...new Set([...headline(a.metrics), ...headline(b.metrics)].map(([k]) => k))];
  if (keys.length === 0) return null;
  return (
    <div>
      <h2 className="text-muted-foreground mb-3 text-sm font-medium">Metrics</h2>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Metric</TableHead>
            <TableHead className="text-right">A</TableHead>
            <TableHead className="text-right">B</TableHead>
            <TableHead className="text-right">B − A</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {keys.map((k) => {
            const va = a.metrics[k];
            const vb = b.metrics[k];
            return (
              <TableRow key={k}>
                <TableCell>{metricLabel(k)}</TableCell>
                <TableCell className="text-right">
                  <MetricValue value={va} err={stderr(a.metrics, k)} />
                </TableCell>
                <TableCell className="text-right">
                  <MetricValue value={vb} err={stderr(b.metrics, k)} />
                </TableCell>
                <TableCell className="text-right">
                  {va != null && vb != null ? <Delta value={vb - va} /> : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

/** Per score, B minus A over the samples both runs scored, with a paired bootstrap interval. An
 * interval that excludes zero is a difference the samples support. */
function Paired({ a, b }: { a: string; b: string }) {
  const cmp = useQuery(q.compare(a, b));
  if (!cmp.data || cmp.data.scores.length === 0) return null;
  const { scores, only_a, only_b } = cmp.data;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-muted-foreground text-sm font-medium">Paired by sample</h2>
        <span className="text-muted-foreground text-xs">
          95% paired bootstrap interval of B − A
          {only_a + only_b > 0 && ` · ${only_a} samples only in A, ${only_b} only in B`}
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Score</TableHead>
            <TableHead className="text-right">n</TableHead>
            <TableHead className="text-right">B − A</TableHead>
            <TableHead className="text-right">95% interval</TableHead>
            <TableHead className="text-right">B higher</TableHead>
            <TableHead className="text-right">B lower</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {scores.map((s) => {
            const sure = s.low > 0 || s.high < 0;
            return (
              <TableRow key={s.name}>
                <TableCell>{s.name}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{s.n}</TableCell>
                <TableCell className="text-right">
                  <Delta value={s.diff} />
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-mono tabular-nums",
                    !sure && "text-muted-foreground",
                  )}
                  title={sure ? "excludes zero" : "includes zero"}
                >
                  [{num(s.low)}, {num(s.high)}]
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">{s.up}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{s.down}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

type Pair = { id: string; input: string; a?: SampleSummary; b?: SampleSummary; changed: boolean };

function Samples({ a, b }: { a: RunDetail; b: RunDetail }) {
  const [sa, sb] = useQueries({ queries: [q.samples(a.id), q.samples(b.id)] });
  const [changedOnly, setChangedOnly] = useQueryState("changed", parseAsBoolean.withDefault(true));
  const [open, setOpen] = useQueryState("sample", parseAsString);

  const names = useMemo(() => [...new Set([...a.scorers, ...b.scorers])], [a, b]);
  const pairs = useMemo<Pair[]>(() => {
    const byId = new Map<string, Pair>();
    for (const s of sa.data ?? [])
      byId.set(s.id, { id: s.id, input: s.input, a: s, changed: false });
    for (const s of sb.data ?? []) {
      const p = byId.get(s.id) ?? { id: s.id, input: s.input, changed: false };
      p.b = s;
      byId.set(s.id, p);
    }
    for (const p of byId.values()) {
      p.changed = !p.a || !p.b || names.some((n) => p.a!.scores[n] !== p.b!.scores[n]);
    }
    return [...byId.values()];
  }, [sa.data, sb.data, names]);

  if (sa.isPending || sb.isPending) return null;
  const rows = changedOnly ? pairs.filter((p) => p.changed) : pairs;
  const changed = pairs.filter((p) => p.changed).length;

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <h2 className="text-muted-foreground text-sm font-medium">Samples</h2>
        <span className="text-muted-foreground text-xs">
          {changed} of {pairs.length} changed
        </span>
        <Button
          className="ml-auto"
          size="sm"
          variant="outline"
          onClick={() => setChangedOnly(!changedOnly)}
        >
          {changedOnly ? "Show all" : "Changed only"}
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12">#</TableHead>
            <TableHead>Input</TableHead>
            {names.map((n) => (
              <TableHead key={n} className="text-center">
                {n} <span className="font-mono">A → B</span>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.id} className="cursor-pointer" onClick={() => setOpen(p.id)}>
              <TableCell className="text-muted-foreground font-mono text-xs whitespace-nowrap">
                {p.id}
              </TableCell>
              <TableCell className="max-w-md truncate">{p.input}</TableCell>
              {names.map((n) => (
                <TableCell key={n} className="text-center whitespace-nowrap">
                  <ScoreCell value={p.a?.scores[n]} />
                  <span className="text-muted-foreground mx-1.5">→</span>
                  <ScoreCell value={p.b?.scores[n]} />
                </TableCell>
              ))}
            </TableRow>
          ))}
          {rows.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell
                colSpan={2 + names.length}
                className="text-muted-foreground py-8 text-center"
              >
                No sample changed between the two runs.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent className="sm:max-w-5xl">
          {open !== null && <SideBySide a={a} b={b} sampleId={open} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function SideBySide({ a, b, sampleId }: { a: RunDetail; b: RunDetail; sampleId: string }) {
  const qa = useQuery(q.sample(a.id, sampleId));
  const qb = useQuery(q.sample(b.id, sampleId));
  return (
    <>
      <div className="border-b px-6 py-4">
        <SheetTitle className="font-semibold">Sample {sampleId}</SheetTitle>
        <SheetDescription className="text-muted-foreground text-sm">
          The same sample in both runs, side by side.
        </SheetDescription>
      </div>
      <div className="grid flex-1 gap-6 overflow-y-auto px-6 py-5 md:grid-cols-2 md:divide-x">
        {[
          ["A", a, qa],
          ["B", b, qb],
        ].map(([label, run, query]) => (
          <div
            key={label as string}
            className="flex min-w-0 flex-col gap-3 md:pr-6 md:last:pr-0 md:[&:last-child]:pl-6"
          >
            <div className="flex items-center gap-2 text-sm">
              <span className="grid size-6 place-items-center rounded-md border font-mono text-xs">
                {label as string}
              </span>
              <span className="truncate font-medium">{(run as RunDetail).name}</span>
            </div>
            <QueryState query={query as typeof qa}>
              {(s) => <Transcript sample={s} compact />}
            </QueryState>
          </div>
        ))}
      </div>
    </>
  );
}
