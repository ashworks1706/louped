"use client";

import { useQuery } from "@tanstack/react-query";
import { Waypoints } from "lucide-react";
import Link from "next/link";
import { parseAsString, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { ExamplesButton } from "@/components/jobs";
import { part } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { API, q } from "@/lib/api";

/** One circuit-tracer graph at a time, drawn by circuit-tracer's viewer, which louped serves. */
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
              body="Attribution graphs over a model's transcoders, from circuit-tracer. The examples draw one over a tiny model's neurons."
            >
              <Button asChild size="sm" variant="outline">
                <Link href="/launch/?id=circuit">Launch a circuit</Link>
              </Button>
              <ExamplesButton />
            </EmptyState>
          );
        }
        const current = all.find((g) => g.slug === slug) ?? all[all.length - 1];
        return (
          <div className="flex flex-col gap-3">
            <NativeSelect
              aria-label="Graph"
              {...part("circuits/graph")}
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
              {...part("circuits/viewer")}
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
