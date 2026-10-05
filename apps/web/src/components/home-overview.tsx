"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Fragment } from "react";

import { ChevronRight } from "lucide-react";

import { ActiveExperiments } from "@/components/experiments-list";
import { LayoutErrors, PluginBlock, RegionGrid, useLayout } from "@/components/layout";
import { arrange, part, partId, useRules } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { RunsList } from "@/components/runs-list";

import { StatusDot } from "@/components/run-badges";
import { Stat, StatGrid } from "@/components/stat-grid";
import { isLive, q } from "@/lib/api";
import { ago } from "@/lib/format";
import { jobHref, runHref } from "@/lib/href";
import { DOMAINS, NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

const WEEK_MS = 7 * 24 * 3600 * 1000;

/** The four numbers that say where the research stands, each opening the list behind it. */
function HomeStats() {
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
  const rule = useRules();
  const stats: { id: string; el: React.ReactNode }[] = [
    {
      id: "live",
      el: (
        <Stat
          label="Live now"
          href="/runs/"
          part="home/stat/live"
          note={
            !live.known
              ? undefined
              : live.jobs.length + live.runs.length === 0
                ? "nothing running"
                : `${live.jobs.length} jobs · ${live.runs.length} runs`
          }
        >
          {live.known ? live.jobs.length + live.runs.length : "—"}
        </Stat>
      ),
    },
    {
      id: "active",
      el: (
        <Stat
          label="Active questions"
          href="/behavior/experiments/?status=active"
          part="home/stat/active"
          note={experiments.data ? `of ${all.length} experiments` : undefined}
        >
          {n(experiments.data && all.filter((e) => e.status === "active").length)}
        </Stat>
      ),
    },
    {
      id: "answered",
      el: (
        <Stat
          label="Answered"
          href="/behavior/experiments/?status=answered"
          part="home/stat/answered"
          note={
            experiments.data
              ? `${all.filter((e) => e.status === "parked").length} parked`
              : undefined
          }
        >
          {n(experiments.data && all.filter((e) => e.status === "answered").length)}
        </Stat>
      ),
    },
    {
      id: "week",
      el: (
        <Stat
          label="Runs this week"
          part="home/stat/week"
          note={newest ? `newest started ${ago(newest)}` : undefined}
        >
          {n(runs.data && week.length)}
        </Stat>
      ),
    },
  ];
  return (
    <StatGrid>
      {arrange(stats, (s) => partId("home/stat", s.id), rule).map((s) => (
        <Fragment key={s.id}>{s.el}</Fragment>
      ))}
    </StatGrid>
  );
}

/** Jobs and runs still going, for the Live strip and the sidebar. Jobs only on a server that
 * launches. known is false while either list is loading or could not be read, so a count is
 * never shown for what was not seen. */
export function useLive() {
  const health = useQuery(q.health());
  const launching = health.data?.launching === true;
  const jobs = useQuery({ ...q.jobs(), retry: false, enabled: launching });
  const runs = useQuery(q.runs());
  return {
    jobs: (jobs.data ?? []).filter((j) => isLive(j.status)),
    runs: (runs.data ?? []).filter((r) => isLive(r.status)),
    known: runs.isSuccess && (!launching || jobs.isSuccess),
  };
}

/** What is running now, with progress; absent when nothing is. */
function LiveNow() {
  const live = useLive();
  if (live.jobs.length + live.runs.length === 0) return null;
  return (
    <section className="flex w-full flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight" {...part("home/live/title")}>
        Running
      </h2>
      <ul className="divide-y rounded-xl border">
        {live.jobs.map((j) => (
          <li key={j.id} {...part(partId("home/live/job", j.id))}>
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
          <li key={r.id} {...part(partId("home/live/run", r.id))}>
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
function DomainCards() {
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
            {...part(partId("home/domain", d.section))}
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
                  {mine.length === 1 ? "question" : "questions"} ·{" "}
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

const MORE =
  "text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline";

/** Home's region: where the research stands, in the blocks the layout lists. */
export function HomeBlocks() {
  const layout = useLayout(null);
  const rule = useRules();
  if (!layout.data) return <QueryState query={layout}>{() => null}</QueryState>;
  return (
    <div>
      <LayoutErrors page={layout.data} />
      <RegionGrid
        region="home"
        roomy
        blocks={layout.data.regions.home}
        render={(b) => {
          switch (b.block) {
            case "stats":
              return { body: <HomeStats /> };
            case "live":
              return { body: <LiveNow /> };
            case "domains":
              return { title: "Domains", body: <DomainCards /> };
            case "active":
              return {
                title: "Active questions",
                body: (
                  <>
                    <ActiveExperiments />
                    <div className="flex gap-4">
                      <Link
                        href="/behavior/experiments/"
                        className={cn(MORE, rule("home/more/behavior").hidden && "hidden")}
                        {...part("home/more/behavior")}
                      >
                        Behavior experiments
                      </Link>
                      <Link
                        href="/efficiency/experiments/"
                        className={cn(MORE, rule("home/more/efficiency").hidden && "hidden")}
                        {...part("home/more/efficiency")}
                      >
                        Efficiency experiments
                      </Link>
                    </div>
                  </>
                ),
              };
            case "latest":
              return {
                title: "Latest runs",
                body: (
                  <>
                    <RunsList limit={8} compact />
                    <Link
                      href="/runs/"
                      className={cn(MORE, rule("home/more/runs").hidden && "hidden")}
                      {...part("home/more/runs")}
                    >
                      All runs
                    </Link>
                  </>
                ),
              };
            case "plugin":
              return { body: <PluginBlock b={b} page="index.html" /> };
            default:
              return null;
          }
        }}
      />
    </div>
  );
}
