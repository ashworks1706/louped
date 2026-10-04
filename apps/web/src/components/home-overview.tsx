"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ChevronRight } from "lucide-react";

import { StatusDot } from "@/components/run-badges";
import { Stat, StatGrid } from "@/components/stat-grid";
import { isLive, q } from "@/lib/api";
import { ago } from "@/lib/format";
import { jobHref, runHref } from "@/lib/href";
import { DOMAINS, NAV } from "@/lib/nav";

const WEEK_MS = 7 * 24 * 3600 * 1000;

/** The four numbers that say where the research stands, each opening the list behind it. */
export function HomeStats() {
  const experiments = useQuery(q.experiments());
  const runs = useQuery(q.runs());
  const live = useLive();
  const all = experiments.data ?? [];
  const allRuns = runs.data ?? [];
  // As of the last fetch, so the count is the data's, not the moment of this render.
  const asOf = runs.dataUpdatedAt;
  const week = allRuns.filter((r) => r.created && asOf - Date.parse(r.created) < WEEK_MS);
  const newest = allRuns.reduce<string | null>(
    (m, r) => (r.created && (!m || r.created > m) ? r.created : m),
    null,
  );
  const n = (count: number | undefined) => (count === undefined ? "—" : count);
  return (
    <StatGrid>
      <Stat
        label="Live now"
        href="/runs/"
        note={
          !runs.data
            ? undefined
            : live.jobs.length + live.runs.length === 0
              ? "nothing running"
              : `${live.jobs.length} jobs · ${live.runs.length} runs`
        }
      >
        {runs.data ? live.jobs.length + live.runs.length : "—"}
      </Stat>
      <Stat
        label="Active questions"
        href="/behavior/experiments/?status=active"
        note={experiments.data ? `of ${all.length} experiments` : undefined}
      >
        {n(experiments.data && all.filter((e) => e.status === "active").length)}
      </Stat>
      <Stat
        label="Answered"
        href="/behavior/experiments/?status=answered"
        note={
          experiments.data ? `${all.filter((e) => e.status === "parked").length} parked` : undefined
        }
      >
        {n(experiments.data && all.filter((e) => e.status === "answered").length)}
      </Stat>
      <Stat label="Runs this week" note={newest ? `newest started ${ago(newest)}` : undefined}>
        {n(runs.data && week.length)}
      </Stat>
    </StatGrid>
  );
}

/** Jobs and runs still going, for the Live strip and the sidebar. Jobs only on a server that
 * launches. */
export function useLive() {
  const health = useQuery(q.health());
  const jobs = useQuery({ ...q.jobs(), retry: false, enabled: health.data?.launching === true });
  const runs = useQuery(q.runs());
  return {
    jobs: (jobs.data ?? []).filter((j) => isLive(j.status)),
    runs: (runs.data ?? []).filter((r) => isLive(r.status)),
  };
}

/** What is running now, with progress; absent when nothing is. */
export function LiveNow() {
  const live = useLive();
  if (live.jobs.length + live.runs.length === 0) return null;
  return (
    <section className="flex w-full flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight">Running</h2>
      <ul className="divide-y rounded-xl border">
        {live.jobs.map((j) => (
          <li key={j.id}>
            <Link
              href={jobHref(j.id)}
              className="hover:bg-accent/40 flex items-center gap-3 px-4 py-3 text-sm transition-colors"
            >
              <span className="text-muted-foreground w-16 text-xs">job</span>
              <span className="min-w-0 flex-1 truncate font-mono">{j.title}</span>
              <StatusDot status={j.status} />
              <span className="text-muted-foreground w-24 text-right text-xs">
                {ago(j.started ?? j.created)}
              </span>
            </Link>
          </li>
        ))}
        {live.runs.map((r) => (
          <li key={r.id}>
            <Link
              href={runHref(r.id)}
              className="hover:bg-accent/40 flex items-center gap-3 px-4 py-3 text-sm transition-colors"
            >
              <span className="text-muted-foreground w-16 text-xs">{r.kind}</span>
              <span className="min-w-0 flex-1 truncate">
                {r.name}
                {r.experiment && <span className="text-muted-foreground"> · {r.experiment}</span>}
              </span>
              <StatusDot status={r.status} samples={r.samples} total={r.total} />
              <span className="text-muted-foreground w-24 text-right text-xs">
                {ago(r.created)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The two research domains, each opening its own section, with how many questions it holds. */
export function DomainCards() {
  const experiments = useQuery(q.experiments());
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {DOMAINS.map((d) => {
        const overview = NAV.find((n) => n.section === d.section);
        const tools = NAV.filter((n) => n.section === d.section).slice(2);
        const mine = (experiments.data ?? []).filter((e) =>
          d.section === "behavior" ? e.axis !== "efficiency" : e.axis === "efficiency",
        );
        const active = mine.filter((e) => e.status === "active").length;
        return (
          <Link
            key={d.section}
            href={overview?.href ?? "/"}
            className="hover:bg-accent/40 focus-visible:ring-ring/50 group flex flex-col gap-3 rounded-xl border p-5 transition-colors outline-none focus-visible:ring-[3px]"
          >
            <span className="flex items-center gap-2 font-medium">
              <d.icon className="text-muted-foreground size-4" />
              {d.title}
              <ChevronRight className="text-muted-foreground group-hover:text-foreground ml-auto size-4 transition-colors" />
            </span>
            <span className="text-muted-foreground text-sm">{overview?.description}</span>
            <span className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              {experiments.data && (
                <span>
                  <span className="text-foreground font-mono tabular-nums">{mine.length}</span>{" "}
                  questions ·{" "}
                  <span className="text-foreground font-mono tabular-nums">{active}</span> active
                </span>
              )}
              <span>{tools.map((t) => t.title).join(" · ")}</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
