"use client";

import { useQuery } from "@tanstack/react-query";
import { ListTree } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { EmptyState } from "@/components/empty-state";
import { ExamplesButton } from "@/components/examples-button";
import { QueryState } from "@/components/query-state";
import { RunsTable } from "@/components/runs-table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AxisFilter, onAxis } from "@/components/experiments-list";
import { q } from "@/lib/api";
import { useAxis, useProject } from "@/lib/scope";

/** Runs, newest first: the sidebar's project's and the ?axis= axis's, or all of them. */
export function RunsList(props: { limit?: number; compact?: boolean }) {
  // the scope is read from the address, which a static page reads under Suspense
  return (
    <Suspense fallback={<Skeleton className="h-10 w-full" />}>
      <ScopedRuns {...props} />
    </Suspense>
  );
}

function ScopedRuns({ limit, compact = false }: { limit?: number; compact?: boolean }) {
  const runs = useQuery(q.runs());
  const [project] = useProject();
  const [axis] = useAxis();
  const scoping = project != null || axis != null;
  const experiments = useQuery({ ...q.experiments(), enabled: scoping });
  const inScope = new Set(
    (experiments.data ?? [])
      .filter((e) => onAxis(e, axis) && (project == null || e.project === project))
      .map((e) => e.name),
  );
  return (
    <QueryState query={runs}>
      {(all) => {
        const shown = scoping
          ? all.filter((r) => r.experiment != null && inScope.has(r.experiment))
          : all;
        return shown.length === 0 && scoping && all.length > 0 ? (
          <p className="text-muted-foreground text-sm">
            No runs{project ? ` in ${project}` : ""}
            {axis ? ` on ${axis}` : ""} yet.
          </p>
        ) : shown.length === 0 ? (
          <EmptyState
            icon={ListTree}
            title="No runs yet"
            body="Launch a script, or load example runs from a tiny model trained on this machine."
          >
            <Button asChild size="sm" variant="outline">
              <Link href="/launch/">Launch a run</Link>
            </Button>
            <ExamplesButton />
          </EmptyState>
        ) : (
          // The table keeps its filters in the URL, which a static page reads under Suspense.
          <Suspense fallback={<Skeleton className="h-10 w-full" />}>
            <div className="flex flex-col gap-3">
              {!compact && <AxisFilter area="runs" />}
              <RunsTable runs={limit ? shown.slice(0, limit) : shown} compact={compact} />
            </div>
          </Suspense>
        );
      }}
    </QueryState>
  );
}
