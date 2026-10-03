"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Plus } from "lucide-react";
import Link from "next/link";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { MetricValue } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { q, type Experiment } from "@/lib/api";
import { ago, headline, metricLabel } from "@/lib/format";
import { experimentHref, runHref } from "@/lib/href";

type Status = Experiment["status"];

/** The two research domains and the checks, in page order, with what each one asks. */
const AXES: { axis: Experiment["axis"]; title: string; about: string }[] = [
  { axis: "behavior", title: "Behavior", about: "What models do, and why." },
  { axis: "efficiency", title: "Efficiency", about: "What it costs to run them." },
  {
    axis: "checks",
    title: "Checks",
    about: "Known results reproduced, so the rest can be trusted.",
  },
];

const FILTERS = ["all", "active", "parked", "answered"] as const;

/** Every experiment grouped by axis and domain, filtered by status through ?status=. */
export function ExperimentsList() {
  const [status, setStatus] = useQueryState(
    "status",
    parseAsStringLiteral(FILTERS).withDefault("all"),
  );
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(all) =>
        all.length === 0 ? (
          <NoExperiments />
        ) : (
          <Tabs value={status} onValueChange={(v) => void setStatus(v as typeof status)}>
            <div className="flex items-center justify-between gap-3">
              <TabsList>
                {FILTERS.map((f) => {
                  const n = f === "all" ? all.length : all.filter((e) => e.status === f).length;
                  return (
                    <TabsTrigger
                      key={f}
                      value={f}
                      className="capitalize"
                      aria-label={`${f} (${n})`}
                    >
                      {f}
                      <span className="text-muted-foreground ml-1.5 font-mono text-[11px] tabular-nums">
                        {n}
                      </span>
                    </TabsTrigger>
                  );
                })}
              </TabsList>
              <Button variant="outline" size="sm" asChild>
                <Link href="/launch/?id=new">
                  <Plus /> New
                </Link>
              </Button>
            </div>
            {FILTERS.map((f) => {
              const shown = f === "all" ? all : all.filter((e) => e.status === f);
              return (
                <TabsContent key={f} value={f} className="flex flex-col gap-10 pt-10">
                  {shown.length > 0 ? (
                    <ByAxis experiments={shown} />
                  ) : (
                    <div className="flex items-center gap-3">
                      <p className="text-muted-foreground text-sm">No {f} experiments.</p>
                      <Button variant="outline" size="sm" onClick={() => void setStatus("all")}>
                        Show all
                      </Button>
                    </div>
                  )}
                </TabsContent>
              );
            })}
          </Tabs>
        )
      }
    </QueryState>
  );
}

/** The questions being worked on now, for Home. */
export function ActiveExperiments() {
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(all) => {
        if (all.length === 0) return <NoExperiments />;
        const active = all.filter((e) => e.status === "active");
        return active.length === 0 ? (
          <EmptyState
            icon={FlaskConical}
            title="No active questions"
            body="Mark one active in its README, or start one."
            action={{ href: "/launch/?id=new", label: "New experiment" }}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {active.map((e) => (
              <ExperimentCard key={e.name} experiment={e} heading="h3" showDomain />
            ))}
          </div>
        );
      }}
    </QueryState>
  );
}

function NoExperiments() {
  return (
    <EmptyState
      icon={FlaskConical}
      title="No experiments yet"
      body="Each question is a folder under experiments/."
      action={{ href: "/launch/?id=new", label: "New experiment" }}
    />
  );
}

function ByAxis({ experiments }: { experiments: Experiment[] }) {
  return (
    <>
      {AXES.map(({ axis, title, about }) => {
        const inAxis = experiments.filter((e) => e.axis === axis);
        if (inAxis.length === 0) return null;
        return (
          <section key={axis} className="flex flex-col gap-6">
            <div className="flex flex-col gap-0.5 border-b pb-3">
              <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
              <p className="text-muted-foreground text-sm">{about}</p>
            </div>
            <DomainGroups experiments={inAxis} heading="h3" />
          </section>
        );
      })}
    </>
  );
}

/** Experiments under a heading per domain, in the store's domain order. */
function DomainGroups({
  experiments,
  heading,
}: {
  experiments: Experiment[];
  heading: "h2" | "h3";
}) {
  const Heading = heading;
  const domains = [...new Set(experiments.map((e) => e.domain))];
  return domains.map((domain) => {
    const group = experiments.filter((e) => e.domain === domain);
    return (
      <div key={domain} className="flex flex-col gap-3">
        <Heading className="text-muted-foreground text-sm font-medium">
          {group[0].domain_title}
        </Heading>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {group.map((e) => (
            <ExperimentCard key={e.name} experiment={e} heading={heading === "h2" ? "h3" : "h4"} />
          ))}
        </div>
      </div>
    );
  });
}

/** One research domain's questions, for its overview page. */
export function AxisExperiments({ axis }: { axis: Experiment["axis"] }) {
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(all) => {
        const mine = all.filter((e) => e.axis === axis);
        if (mine.length === 0)
          return (
            <EmptyState
              icon={FlaskConical}
              title="No questions here yet"
              action={{ href: "/launch/?id=new", label: "New experiment" }}
            />
          );
        return (
          <div className="flex flex-col gap-6">
            <DomainGroups experiments={mine} heading="h3" />
          </div>
        );
      }}
    </QueryState>
  );
}

/** Neutral marks only: positive and negative are reserved for deltas. */
export function StatusLabel({ status }: { status: Status }) {
  const mark =
    status === "active"
      ? "bg-foreground"
      : status === "answered"
        ? "bg-muted-foreground"
        : "border-muted-foreground border";
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span className={`size-1.5 rounded-full ${mark}`} />
      {status}
    </span>
  );
}

/** Runs shown per card; the rest are counted and live on the Runs page. */
const RUNS_SHOWN = 3;

function ExperimentCard({
  experiment: e,
  heading: Heading,
  showDomain = false,
}: {
  experiment: Experiment;
  heading: "h3" | "h4";
  showDomain?: boolean;
}) {
  return (
    <article className="flex min-w-0 flex-col rounded-xl border">
      <Link
        href={experimentHref(e.name)}
        aria-labelledby={`exp-${e.name}`}
        className="hover:bg-accent/40 focus-visible:ring-ring/50 flex flex-col gap-1.5 rounded-t-xl border-b p-5 transition-colors outline-none focus-visible:ring-[3px]"
      >
        <div className="flex items-center gap-3">
          <Heading
            id={`exp-${e.name}`}
            className="text-muted-foreground min-w-0 flex-1 truncate font-mono text-sm font-normal"
          >
            {e.name}
          </Heading>
          <StatusLabel status={e.status} />
        </div>
        {showDomain && <p className="text-muted-foreground text-xs">{e.domain_title}</p>}
        <p className="text-[15px] leading-snug font-medium">
          {e.question ?? "No question written yet."}
        </p>
        {e.result && (
          <p className="text-muted-foreground line-clamp-3 text-sm leading-relaxed">{e.result}</p>
        )}
      </Link>
      {e.runs.length === 0 ? (
        <p className="text-muted-foreground p-5 text-sm">No runs yet.</p>
      ) : (
        <ul className="divide-y">
          {e.runs.slice(0, RUNS_SHOWN).map((r) => {
            const m = headline(r.metrics);
            const last = m[m.length - 1];
            return (
              <li key={r.id}>
                <Link
                  href={runHref(r.id)}
                  className="hover:bg-accent/40 flex items-center gap-3 px-5 py-3 text-sm transition-colors"
                >
                  <span className="min-w-0 flex-1 truncate">{r.name}</span>
                  {last && (
                    <span className="flex flex-col items-end">
                      <MetricValue value={last[1]} />
                      <span className="text-muted-foreground text-[11px]">
                        {metricLabel(last[0])}
                      </span>
                    </span>
                  )}
                  <span className="text-muted-foreground w-20 text-right text-xs">
                    {ago(r.created)}
                  </span>
                </Link>
              </li>
            );
          })}
          {e.runs.length > RUNS_SHOWN && (
            <li>
              <Link
                href={experimentHref(e.name, "runs")}
                className="text-muted-foreground hover:text-foreground block px-5 py-3 text-xs transition-colors"
              >
                <span className="font-mono tabular-nums">{e.runs.length - RUNS_SHOWN}</span> more
                runs
              </Link>
            </li>
          )}
        </ul>
      )}
    </article>
  );
}
