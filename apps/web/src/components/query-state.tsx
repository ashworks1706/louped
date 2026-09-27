"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { ServerOff } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";

/** Loading, API-down and not-found states for one query, so pages only render the happy path. */
export function QueryState<T>({
  query,
  children,
  rows = 4,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => React.ReactNode;
  rows?: number;
}) {
  if (query.isPending) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) {
      return (
        <p className="text-muted-foreground rounded-xl border px-4 py-6 text-sm">
          Not found. It may have been deleted, or the link is from another machine.
        </p>
      );
    }
    return (
      <EmptyState
        icon={ServerOff}
        title="Can't reach the API"
        body="The UI reads everything from loupe's API. Start it, and this page fills in."
        command="just serve"
      />
    );
  }
  return <>{children(query.data)}</>;
}
