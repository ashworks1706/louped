"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { part, partId } from "@/components/parts";
import { MetricValue } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { q, type Experiment } from "@/lib/api";
import { ago, headline, metricLabel } from "@/lib/format";
import { experimentHref } from "@/lib/href";
import { cn } from "@/lib/utils";

type Status = Experiment["status"];
type Axis = "behavior" | "efficiency";

const FILTERS = ["all", "active", "parked", "answered"] as const;

/** A domain's experiments; the checks file under behavior. */
const inAxis = (e: Experiment, axis: Axis) =>
  axis === "behavior" ? e.axis !== "efficiency" : e.axis === "efficiency";

/** The domain an empty state's command names, one that exists on each axis. */
const EXAMPLE_DOMAIN: Record<Axis, string> = { behavior: "honesty", efficiency: "inference" };

/** One axis's experiments grouped by domain, filtered by status through ?status=. */
export function ExperimentsList({ axis }: { axis: Axis }) {
  const [status, setStatus] = useQueryState(
    "status",
    parseAsStringLiteral(FILTERS).withDefault("all"),
  );
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(everything) => {
        const all = everything.filter((e) => inAxis(e, axis));
        if (all.length === 0) return <NoExperiments axis={axis} />;
        const shown = status === "all" ? all : all.filter((e) => e.status === status);
        return (
          <div className="flex flex-col gap-8">
            <div
              role="group"
              aria-label="Status"
              className="bg-muted/50 flex w-fit items-center gap-0.5 rounded-lg border p-0.5"
            >
              {FILTERS.map((f) => {
                const n = f === "all" ? all.length : all.filter((e) => e.status === f).length;
                return (
                  <button
                    key={f}
                    type="button"
                    {...part(partId("experiments/filter", f))}
                    aria-pressed={status === f}
                    onClick={() => void setStatus(f === "all" ? null : f)}
                    className={cn(
                      "focus-visible:ring-ring/30 flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs capitalize outline-none focus-visible:ring-[3px]",
                      status === f
                        ? "bg-background text-foreground ring-border ring-1"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {f}
                    <span className="font-mono text-[11px] tabular-nums opacity-70">{n}</span>
                  </button>
                );
              })}
            </div>
            {shown.length > 0 ? (
              <DomainGroups experiments={shown} />
            ) : (
              <p className="text-muted-foreground text-sm">No {status} experiments.</p>
            )}
          </div>
        );
      }}
    </QueryState>
  );
}

/** The questions being worked on now, across both domains, for Home. */
export function ActiveExperiments() {
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(all) => {
        const active = all.filter((e) => e.status === "active");
        return active.length === 0 ? (
          <p className="text-muted-foreground rounded-xl border border-dashed px-4 py-6 text-center text-sm">
            No active questions. A README with <span className="font-mono">status: active</span>{" "}
            puts one here.
          </p>
        ) : (
          <CardGrid>
            {active.map((e) => (
              <ExperimentCard key={e.name} experiment={e} showDomain />
            ))}
          </CardGrid>
        );
      }}
    </QueryState>
  );
}

/** One domain's questions, for its overview page. */
export function AxisExperiments({ axis }: { axis: Axis }) {
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(all) => {
        const mine = all.filter((e) => inAxis(e, axis));
        return mine.length === 0 ? (
          <NoExperiments axis={axis} />
        ) : (
          <CardGrid>
            {mine.map((e) => (
              <ExperimentCard key={e.name} experiment={e} showDomain />
            ))}
          </CardGrid>
        );
      }}
    </QueryState>
  );
}

/** Experiments are folders: the app reads them, an editor or a coding agent writes them. */
function NoExperiments({ axis }: { axis: Axis }) {
  return (
    <EmptyState
      icon={FlaskConical}
      title="No experiments here yet"
      body="An experiment is a folder under experiments/ with a README naming its domain. It shows up here as soon as the folder exists."
      command={`louped new my-question --domain ${EXAMPLE_DOMAIN[axis]}`}
    />
  );
}

function CardGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>;
}

/** Experiments under a heading per domain, in the store's domain order. */
function DomainGroups({ experiments }: { experiments: Experiment[] }) {
  const domains = [...new Set(experiments.map((e) => e.domain))];
  return domains.map((domain) => {
    const group = experiments.filter((e) => e.domain === domain);
    return (
      <section key={domain} className="flex flex-col gap-3">
        <h2
          className="text-muted-foreground flex items-center gap-2 text-xs font-medium"
          {...part(partId("experiments/domain", domain))}
        >
          {group[0].domain_title}
          <span className="font-mono tabular-nums">{group.length}</span>
        </h2>
        <CardGrid>
          {group.map((e) => (
            <ExperimentCard key={e.name} experiment={e} />
          ))}
        </CardGrid>
      </section>
    );
  });
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

/** A question at a glance: its name, two lines of the question, and where its runs stand. The
 * whole text is on its page. */
function ExperimentCard({
  experiment: e,
  showDomain = false,
}: {
  experiment: Experiment;
  showDomain?: boolean;
}) {
  const last = e.runs[0];
  const metric = last ? headline(last.metrics).at(-1) : undefined;
  return (
    <Link
      href={experimentHref(e.name, e.axis)}
      {...part(partId("experiments/row", e.name))}
      title={e.question ?? e.name}
      className="hover:bg-accent/40 focus-visible:ring-ring/50 flex min-w-0 flex-col gap-2 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
    >
      <div className="flex items-center gap-3">
        <h3 className="min-w-0 flex-1 truncate font-mono text-sm font-medium">{e.name}</h3>
        <StatusLabel status={e.status} />
      </div>
      {showDomain && <p className="text-muted-foreground -mt-1 text-xs">{e.domain_title}</p>}
      <p className="text-muted-foreground line-clamp-2 text-sm leading-snug">
        {e.question ?? "No question written yet."}
      </p>
      <div className="text-muted-foreground mt-auto flex flex-col gap-1.5 border-t pt-2.5 text-xs">
        <div className="flex items-center gap-3 whitespace-nowrap">
          <span>
            <span className="text-foreground font-mono tabular-nums">{e.runs.length}</span>{" "}
            {e.runs.length === 1 ? "run" : "runs"}
          </span>
          {last && <span className="truncate">last {ago(last.created)}</span>}
        </div>
        {metric && (
          <div className="flex min-w-0 items-center justify-between gap-2">
            <span className="truncate" title={metricLabel(metric[0])}>
              {metricLabel(metric[0])}
            </span>
            <MetricValue value={metric[1]} />
          </div>
        )}
      </div>
    </Link>
  );
}
