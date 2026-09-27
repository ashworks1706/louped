"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { MetricValue } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { runHref } from "@/components/runs-table";
import { q } from "@/lib/api";
import { ago, headline, metricLabel } from "@/lib/format";

export function ExperimentsList() {
  const experiments = useQuery(q.experiments());
  return (
    <QueryState query={experiments}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={FlaskConical}
            title="No experiments yet"
            body="Each folder under experiments/ becomes a card here, with its question and the runs that answer it."
            command="just new-experiment my-question"
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {all.map((e) => (
              <article key={e.name} className="flex flex-col rounded-xl border">
                <div className="flex flex-col gap-1.5 border-b p-5">
                  <h2 className="text-muted-foreground font-mono text-sm">{e.name}</h2>
                  <p className="text-[15px] leading-snug font-medium">
                    {e.question ??
                      "No question written yet. Add one under ## Question in its README."}
                  </p>
                </div>
                {e.runs.length === 0 ? (
                  <p className="text-muted-foreground p-5 text-sm">No runs yet.</p>
                ) : (
                  <ul className="divide-y">
                    {e.runs.map((r) => {
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
                  </ul>
                )}
              </article>
            ))}
          </div>
        )
      }
    </QueryState>
  );
}
