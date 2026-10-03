"use client";

import { useQuery } from "@tanstack/react-query";
import { ListTree } from "lucide-react";
import { Suspense } from "react";

import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { RunsTable } from "@/components/runs-table";
import { Skeleton } from "@/components/ui/skeleton";
import { q, type Experiment, type RunSummary } from "@/lib/api";

/** Runs, newest first: all of them, or one kind's, or those of one domain's experiments. */
export function RunsList({
  limit,
  compact = false,
  kind,
  axis,
}: {
  limit?: number;
  compact?: boolean;
  kind?: RunSummary["kind"];
  axis?: Experiment["axis"];
}) {
  const runs = useQuery(q.runs());
  const experiments = useQuery({ ...q.experiments(), enabled: axis != null });
  const inAxis = new Set(
    (experiments.data ?? []).filter((e) => e.axis === axis).map((e) => e.name),
  );
  return (
    <QueryState query={runs}>
      {(all) => {
        const shown = all.filter(
          (r) =>
            (kind == null || r.kind === kind) &&
            (axis == null || (r.experiment != null && inAxis.has(r.experiment))),
        );
        return shown.length === 0 ? (
          <EmptyState
            icon={ListTree}
            title="No runs yet"
            action={{ href: "/launch/", label: "Launch a run" }}
          />
        ) : (
          // The table keeps its filters in the URL, which a static page reads under Suspense.
          <Suspense fallback={<Skeleton className="h-10 w-full" />}>
            <RunsTable runs={limit ? shown.slice(0, limit) : shown} compact={compact} />
          </Suspense>
        );
      }}
    </QueryState>
  );
}
