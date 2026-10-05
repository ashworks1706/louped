"use client";

import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { MetricName, Term } from "@/components/term";
import { ArrowLeftRight, GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { parseAsBoolean, parseAsString, useQueryState, useQueryStates } from "nuqs";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { HistoryCharts } from "@/components/history-chart";
import { Part, PartData, part, partId } from "@/components/parts";
import { Delta, MetricValue, ScoreCell } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { runHref } from "@/lib/href";
import { Transcript } from "@/components/transcript";
import { Button } from "@/components/ui/button";
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
import { launch, q, type RunDetail, type SampleSummary } from "@/lib/api";
import { ago, headline, isEfficiency, isSystem, lowerIsBetter, num, stderr } from "@/lib/format";
import { cn } from "@/lib/utils";

export function CompareView() {
  const [{ a, b }, set] = useQueryStates({ a: parseAsString, b: parseAsString });
  return (
    <>
      <section className="mx-auto max-w-6xl px-6 pt-8">
        <Pickers a={a} b={b} set={(next) => void set(next)} />
      </section>
      {a && b ? (
        <Loaded a={a} b={b} />
      ) : (
        <section className="mx-auto max-w-6xl px-6 py-8">
          <EmptyState
            icon={GitCompareArrows}
            title="Pick a baseline and a changed run"
            body="Usually one eval, before and after a change."
            action={{ href: "/launch/?id=eval", label: "Launch an eval" }}
          />
        </section>
      )}
    </>
  );
}

/** The two runs, chosen here or from Runs; the URL holds them. */
function Pickers({
  a,
  b,
  set,
}: {
  a: string | null;
  b: string | null;
  set: (next: { a?: string | null; b?: string | null }) => void;
}) {
  const runs = useQuery(q.runs());
  const all = runs.data ?? [];
  // The baseline's experiment first, since the changed run is usually its sibling.
  const home = all.find((r) => r.id === a)?.experiment;
  const groups = [...new Set(all.map((r) => r.experiment ?? "no experiment"))].sort((x, y) =>
    x === home ? -1 : y === home ? 1 : x.localeCompare(y),
  );
  // other is the run picked on the other side, which this side cannot pick too. A picked id
  // the list does not hold yet (still loading, or gone) is kept as its own option.
  const options = (picked: string | null, other: string | null) => (
    <>
      {picked && !all.some((r) => r.id === picked) && <option value={picked}>{picked}</option>}
      {groups.map((g) => (
        <optgroup key={g} label={g}>
          {all
            .filter((r) => (r.experiment ?? "no experiment") === g)
            .map((r) => (
              <option key={r.id} value={r.id} disabled={r.id === other}>
                {r.name} · {r.kind} · {ago(r.created)}
              </option>
            ))}
        </optgroup>
      ))}
    </>
  );
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex min-w-0 flex-col gap-1.5" {...part("compare/pick/a")}>
        <span className="text-muted-foreground text-xs">Baseline</span>
        <NativeSelect
          className="max-w-80"
          aria-label="Baseline"
          value={a ?? ""}
          onChange={(e) => set({ a: e.target.value || null })}
        >
          <option value="">Pick a run…</option>
          {options(a, b)}
        </NativeSelect>
      </label>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label="Swap baseline and changed"
        {...part("compare/pick/swap")}
        disabled={!a && !b}
        onClick={() => set({ a: b, b: a })}
      >
        <ArrowLeftRight />
      </Button>
      <label className="flex min-w-0 flex-col gap-1.5" {...part("compare/pick/b")}>
        <span className="text-muted-foreground text-xs">Changed</span>
        <NativeSelect
          className="max-w-80"
          aria-label="Changed"
          value={b ?? ""}
          onChange={(e) => set({ b: e.target.value || null })}
        >
          <option value="">Pick a run…</option>
          {options(b, a)}
        </NativeSelect>
      </label>
    </div>
  );
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
          <Curves a={ra.data} b={rb.data} />
          {ra.data.kind === "eval" && rb.data.kind === "eval" && (
            <>
              <Judge a={a} b={b} />
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
            {...part(partId("compare/run", (label as string).toLowerCase()))}
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

/** Both runs' curves on each metric both logged over steps, such as two trainings' loss. */
function Curves({ a, b }: { a: RunDetail; b: RunDetail }) {
  const chart = <HistoryCharts history={b.history} against={a.history} />;
  const both = Object.keys(b.history).some(
    (k) => !isSystem(k) && b.history[k].length > 1 && (a.history[k]?.length ?? 0) > 1,
  );
  if (!both) return null;
  return (
    <Part id="compare/section/curves">
      <h2 className="text-muted-foreground mb-3 text-sm font-medium">Curves</h2>
      {chart}
    </Part>
  );
}

/** Queue a judge reading B against A sample by sample; its run lands beside them. The judge is
 * louped's own or one of the project's judges/<name>.py. */
function Judge({ a, b }: { a: string; b: string }) {
  const router = useRouter();
  const judges = useQuery(q.judges());
  const [name, setName] = useState("default");
  const go = useMutation({
    mutationFn: () => launch({ id: "judge", options: { a, b, "--judge": name } }),
    onSuccess: (job) => router.push(`/launch/?id=judge&job=${encodeURIComponent(job.id)}`),
  });
  const chosen = judges.data?.find((j) => j.name === name);
  return (
    <Part id="compare/section/judge" className="-mt-4 flex items-center justify-end gap-2">
      {(go.error ?? judges.error) && (
        <span className="text-negative text-xs">{(go.error ?? judges.error)!.message}</span>
      )}
      {(judges.data?.length ?? 0) > 1 && (
        <NativeSelect
          aria-label="Judge"
          value={name}
          onChange={(e) => setName(e.target.value)}
          title={chosen?.about ?? chosen?.criterion}
          className="h-8 w-auto font-mono text-xs"
          {...part("compare/pick/judge")}
        >
          {judges.data!.map((j) => (
            <option key={j.name} value={j.name}>
              {j.name}
            </option>
          ))}
        </NativeSelect>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={go.isPending || !!judges.error}
        onClick={() => go.mutate()}
      >
        Judge
      </Button>
      <Help label="What does Judge do?">
        A model reads both runs&apos; answers to each sample, twice with the order swapped, and
        picks the better one by the judge&apos;s criterion. The result is a run with B&apos;s win
        rate. Judges are files in judges/; your agent writes new ones.
      </Help>
    </Part>
  );
}

function Metrics({ a, b }: { a: RunDetail; b: RunDetail }) {
  const keys = [...new Set([...headline(a.metrics), ...headline(b.metrics)].map(([k]) => k))];
  if (keys.length === 0) return null;
  return (
    <Part id="compare/section/metrics">
      <h2 className="text-muted-foreground mb-3 text-sm font-medium">Metrics</h2>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Metric</TableHead>
            <TableHead className="text-right">A</TableHead>
            <TableHead className="text-right">B</TableHead>
            <TableHead className="text-right">
              <Term k="delta">B − A</Term>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {keys.map((k) => {
            const va = a.metrics[k];
            const vb = b.metrics[k];
            return (
              <TableRow key={k} {...part(partId("compare/metric", k))}>
                <TableCell>
                  <MetricName k={k} />
                </TableCell>
                <TableCell className="text-right">
                  <MetricValue value={va} err={stderr(a.metrics, k)} />
                </TableCell>
                <TableCell className="text-right">
                  <MetricValue value={vb} err={stderr(b.metrics, k)} />
                </TableCell>
                <TableCell className="text-right">
                  {va != null && vb != null ? (
                    <Delta value={vb - va} lowerBetter={lowerIsBetter(k)} />
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Part>
  );
}

/** Per score, B minus A over the samples both runs scored, with a paired bootstrap interval. An
 * interval that excludes zero is a difference the samples support. */
function Paired({ a, b }: { a: string; b: string }) {
  const cmp = useQuery(q.compare(a, b));
  const [, setFlip] = useQueryState("flip", parseAsString);
  if (cmp.error) return <p className="text-negative text-sm">{cmp.error.message}</p>;
  if (!cmp.data || cmp.data.scores.length === 0) return null;
  const { scores, only_a, only_b } = cmp.data;
  const ratios = scores.some((s) => isEfficiency(s.name));
  return (
    <Part id="compare/section/paired">
      <PartData
        prefix="compare/score"
        resolve={(id) => scores.find((s) => partId("compare/score", s.name) === id)}
      />
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
            <TableHead className="text-right">
              <Term k="n">n</Term>
            </TableHead>
            <TableHead className="text-right">
              <Term k="delta">B − A</Term>
            </TableHead>
            {ratios && (
              <TableHead className="text-right">
                <Term k="ratio">B ÷ A</Term>
              </TableHead>
            )}
            <TableHead className="text-right">
              <Term k="interval">95% interval</Term>
            </TableHead>
            <TableHead className="text-right">
              <Term k="moved">B higher</Term>
            </TableHead>
            <TableHead className="text-right">B lower</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {scores.map((s) => {
            const sure = s.low > 0 || s.high < 0;
            return (
              <TableRow key={s.name} {...part(partId("compare/score", s.name))}>
                <TableCell>
                  <MetricName k={s.name} />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">{s.n}</TableCell>
                <TableCell className="text-right">
                  <Delta value={s.diff} lowerBetter={lowerIsBetter(s.name)} />
                </TableCell>
                {ratios && (
                  <TableCell
                    className="text-muted-foreground text-right font-mono tabular-nums"
                    title="mean of B over mean of A"
                  >
                    {isEfficiency(s.name) && s.mean_a ? `×${num(s.mean_b / s.mean_a, 2)}` : ""}
                  </TableCell>
                )}
                <TableCell
                  className={cn(
                    "text-right font-mono tabular-nums",
                    !sure && "text-muted-foreground",
                  )}
                  title={sure ? "excludes zero" : "includes zero"}
                >
                  [{num(s.low)}, {num(s.high)}]
                </TableCell>
                {(["up", "down"] as const).map((dir) => (
                  <TableCell key={dir} className="text-right font-mono tabular-nums">
                    <button
                      className="underline-offset-4 hover:underline disabled:no-underline"
                      disabled={s[dir] === 0}
                      onClick={() => void setFlip(`${dir}:${s.name}`)}
                      aria-label={`Show the ${s[dir]} samples where B scored ${dir === "up" ? "higher" : "lower"} on ${s.name}`}
                    >
                      {s[dir]}
                    </button>
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Part>
  );
}

type Pair = { id: string; input: string; a?: SampleSummary; b?: SampleSummary; changed: boolean };

function Samples({ a, b }: { a: RunDetail; b: RunDetail }) {
  const [sa, sb] = useQueries({ queries: [q.samples(a.id), q.samples(b.id)] });
  const [changedOnly, setChangedOnly] = useQueryState("changed", parseAsBoolean.withDefault(true));
  const [open, setOpen] = useQueryState("sample", parseAsString);
  const [flip, setFlip] = useQueryState("flip", parseAsString);

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

  if (sa.isError || sb.isError)
    return <QueryState query={sa.isError ? sa : sb}>{() => null}</QueryState>;
  if (sa.isPending || sb.isPending) return null;
  const [dir, score] = flip
    ? [flip.slice(0, flip.indexOf(":")), flip.slice(flip.indexOf(":") + 1)]
    : [];
  const moved = (p: Pair) => {
    const x = p.a?.scores[score!];
    const y = p.b?.scores[score!];
    return x != null && y != null && (dir === "up" ? y > x : y < x);
  };
  const rows = flip ? pairs.filter(moved) : changedOnly ? pairs.filter((p) => p.changed) : pairs;
  const changed = pairs.filter((p) => p.changed).length;

  return (
    <Part id="compare/section/samples">
      <div className="mb-3 flex items-center gap-3">
        <h2 className="text-muted-foreground text-sm font-medium">Samples</h2>
        <span className="text-muted-foreground text-xs">
          {changed} of {pairs.length} changed
        </span>
        {flip ? (
          <Button className="ml-auto" size="sm" variant="outline" onClick={() => setFlip(null)}>
            B {dir === "up" ? "higher" : "lower"} on {score} · clear
          </Button>
        ) : (
          <Button
            className="ml-auto"
            size="sm"
            variant="outline"
            onClick={() => setChangedOnly(!changedOnly)}
          >
            {changedOnly ? "Show all" : "Changed only"}
          </Button>
        )}
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
            <TableRow
              key={p.id}
              className="cursor-pointer"
              onClick={() => setOpen(p.id)}
              {...part(partId("compare/sample", p.id))}
            >
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
    </Part>
  );
}

function SideBySide({ a, b, sampleId }: { a: RunDetail; b: RunDetail; sampleId: string }) {
  const qa = useQuery(q.sample(a.id, sampleId));
  const qb = useQuery(q.sample(b.id, sampleId));
  return (
    <>
      <div className="border-b px-6 py-4">
        <SheetTitle className="font-semibold" {...part("compare/open/title")}>
          Sample {sampleId}
        </SheetTitle>
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
            {...part(partId("compare/open/side", (label as string).toLowerCase()))}
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
