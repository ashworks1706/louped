"use client";

import { useQuery } from "@tanstack/react-query";
import { ListTree } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { RunsTable } from "@/components/runs-table";
import { q } from "@/lib/api";

export const FIRST_RUN_COMMAND = "python experiments/demo-pressure-mock/run.py";

export function RunsList({ limit, compact = false }: { limit?: number; compact?: boolean }) {
  const runs = useQuery(q.runs());
  return (
    <QueryState query={runs}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={ListTree}
            title="No runs yet"
            body="Eval logs, analyses and training runs appear here as soon as they are written."
            command={FIRST_RUN_COMMAND}
          />
        ) : (
          <RunsTable runs={limit ? all.slice(0, limit) : all} compact={compact} />
        )
      }
    </QueryState>
  );
}
