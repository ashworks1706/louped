"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical, FolderKanban } from "lucide-react";
import Link from "next/link";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { part, partId } from "@/components/parts";
import { MetricValue } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { NewExperiment } from "@/components/new-experiment";
import { q, type Experiment, type Project } from "@/lib/api";
import { ago, headline, metricLabel } from "@/lib/format";
import { experimentHref } from "@/lib/href";
import { AXES, type Axis } from "@/lib/nav";
import { useAxis, useProject } from "@/lib/scope";
import { cn } from "@/lib/utils";

type Status = Experiment["status"] | Project["status"];

const FILTERS = ["all", "active", "parked", "answered"] as const;

/** Whether an experiment is on an axis; the checks file under behavior. */
export const onAxis = (e: Experiment, axis: Axis | null) =>
  axis == null || (axis === "behavior" ? e.axis !== "efficiency" : e.axis === "efficiency");

/** The experiments grouped by domain: the sidebar's project, the axis (?axis=) and the status
 * (?status=) narrow them. */
export function ExperimentsList() {
  const [status, setStatus] = useQueryState(
    "status",
    parseAsStringLiteral(FILTERS).withDefault("all"),
  );
  const [axis] = useAxis();
  const [project] = useProject();
  const health = useQuery(q.health());
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(everything) => {
        const scope = everything.filter(
          (e) => onAxis(e, axis) && (project == null || e.project === project),
        );
        const shown = status === "all" ? scope : scope.filter((e) => e.status === status);
        return (
          <div className="flex flex-col gap-8">
            <div className="flex flex-wrap items-center gap-3">
              <Segmented
                label="Status"
                value={status}
                options={FILTERS.map((f) => ({
                  value: f,
                  title: f,
                  count: f === "all" ? scope.length : scope.filter((e) => e.status === f).length,
                  address: partId("experiments/filter", f),
                }))}
                onChange={(f) => void setStatus(f === "all" ? null : f)}
              />
              <AxisFilter area="experiments" />
              {health.data?.launching && (
                <span className="ml-auto">
                  <NewExperiment project={project} />
                </span>
              )}
            </div>
            {everything.length === 0 ? (
              <NoExperiments />
            ) : shown.length > 0 ? (
              <DomainGroups experiments={shown} showProject={project == null} />
            ) : (
              <p className="text-muted-foreground text-sm">
                No {status === "all" ? "" : `${status} `}experiments
                {project ? ` in ${project}` : ""}
                {axis ? ` on ${axis}` : ""}.
              </p>
            )}
          </div>
        );
      }}
    </QueryState>
  );
}

/** A row of buttons, one pressed: a filter whose options are few. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; title: string; count?: number; address: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="bg-muted/50 flex w-fit items-center gap-0.5 rounded-lg border p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          {...part(o.address)}
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "focus-visible:ring-ring/30 flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs capitalize outline-none focus-visible:ring-[3px]",
            value === o.value
              ? "bg-background text-foreground ring-border ring-1"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.title}
          {o.count != null && (
            <span className="font-mono text-[11px] tabular-nums opacity-70">{o.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

/** Both axes, behavior or efficiency: ?axis=, on any list that has both. */
export function AxisFilter({ area }: { area: string }) {
  const [axis, setAxis] = useAxis();
  return (
    <Segmented
      label="Axis"
      value={axis ?? "both"}
      options={[
        { value: "both", title: "Both", address: partId(`${area}/axis`, "both") },
        ...AXES.map((a) => ({
          value: a.axis,
          title: a.title,
          address: partId(`${area}/axis`, a.axis),
        })),
      ]}
      onChange={(v) => void setAxis(v === "both" ? null : v)}
    />
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

/** Experiments are folders: the app writes one with New experiment; an editor or a coding agent
 * fills it in. */
function NoExperiments() {
  return (
    <EmptyState
      icon={FlaskConical}
      title="No experiments yet"
      body="An experiment is a folder under experiments/ with a README naming its question and domain. New experiment writes one; it shows up here as soon as the folder exists."
      command="louped new my-question --domain honesty"
    />
  );
}

function CardGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>;
}

/** Experiments under a heading per domain, in the store's domain order. */
export function DomainGroups({
  experiments,
  showProject = true,
}: {
  experiments: Experiment[];
  showProject?: boolean;
}) {
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
            <ExperimentCard key={e.name} experiment={e} showProject={showProject} />
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
      : status === "answered" || status === "done"
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
  showProject = true,
}: {
  experiment: Experiment;
  showDomain?: boolean;
  showProject?: boolean;
}) {
  const project = showProject ? e.project : null;
  const last = e.runs[0];
  const metric = last ? headline(last.metrics).at(-1) : undefined;
  return (
    <Link
      href={experimentHref(e.name)}
      {...part(partId("experiments/row", e.name))}
      title={e.question ?? e.name}
      className="hover:bg-accent/40 focus-visible:ring-ring/50 flex min-w-0 flex-col gap-2 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
    >
      <div className="flex items-center gap-3">
        <h3 className="min-w-0 flex-1 truncate font-mono text-sm font-medium">{e.name}</h3>
        <StatusLabel status={e.status} />
      </div>
      {(showDomain || project) && (
        <p className="text-muted-foreground -mt-1 flex min-w-0 items-center gap-2 text-xs">
          {showDomain && <span className="truncate">{e.domain_title}</span>}
          {project && (
            <span
              className="bg-muted inline-flex max-w-full min-w-0 items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[11px]"
              title={`In project ${project}`}
            >
              <FolderKanban className="size-3 shrink-0" />
              <span className="truncate">{project}</span>
            </span>
          )}
        </p>
      )}
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
