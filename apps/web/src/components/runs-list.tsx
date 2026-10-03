"use client";

import { useQuery } from "@tanstack/react-query";
import { ListTree } from "lucide-react";
import { Suspense } from "react";

import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { RunsTable } from "@/components/runs-table";
import { Skeleton } from "@/components/ui/skeleton";
import { q } from "@/lib/api";

export function RunsList({ limit, compact = false }: { limit?: number; compact?: boolean }) {
  const runs = useQuery(q.runs());
  return (
    <QueryState query={runs}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={ListTree}
            title="No runs yet"
            body="Evals, analyses and training runs appear as they are written."
            action={{ href: "/launch/", label: "Launch a run" }}
          />
        ) : (
          // The table keeps its filters in the URL, which a static page reads under Suspense.
          <Suspense fallback={<Skeleton className="h-10 w-full" />}>
            <RunsTable runs={limit ? all.slice(0, limit) : all} compact={compact} />
          </Suspense>
        )
      }
    </QueryState>
  );
}
