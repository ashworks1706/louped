"use client";

import { useQuery } from "@tanstack/react-query";
import { Waypoints } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { NativeSelect } from "@/components/ui/native-select";
import { API, q } from "@/lib/api";

/** One circuit-tracer graph at a time, drawn by circuit-tracer's viewer, which loupe serves. */
export function CircuitsView() {
  const graphs = useQuery(q.graphs());
  const [slug, setSlug] = useQueryState("slug", parseAsString);
  return (
    <QueryState query={graphs}>
      {(all) => {
        if (all.length === 0) {
          return (
            <EmptyState
              icon={Waypoints}
              title="No graphs"
              body="Attribution graphs over a model's transcoders, from circuit-tracer."
              action={{ href: "/launch/?id=circuit", label: "Launch a circuit" }}
            />
          );
        }
        const current = all.find((g) => g.slug === slug) ?? all[all.length - 1];
        return (
          <div className="flex flex-col gap-3">
            <NativeSelect
              aria-label="Graph"
              value={current.slug}
              onChange={(e) => void setSlug(e.target.value)}
              className="max-w-full"
            >
              {all.map((g) => (
                <option key={g.slug} value={g.slug}>
                  {g.slug}: {g.prompt}
                </option>
              ))}
            </NativeSelect>
            <iframe
              key={current.slug}
              title={`Attribution graph ${current.slug}`}
              src={`${API}/circuit/?slug=${encodeURIComponent(current.slug)}`}
              className="h-[calc(100svh-14rem)] min-h-[32rem] w-full rounded-xl border"
            />
          </div>
        );
      }}
    </QueryState>
  );
}
