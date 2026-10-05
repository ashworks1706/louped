"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { q, type Trace } from "@/lib/api";
import { itemHref } from "@/lib/href";

/** Where an item step's record sits: its run, item folder and key, from its ref. */
const ITEM = /^run:([^/#]+)\/([^#]+)#([\s\S]+)$/;

/** The Items tab with a traced item open, from the trace's item step. */
export function itemPage(trace: Trace): string | null {
  const step = trace.steps.find((s) => s.what === "item");
  const m = step && ITEM.exec(step.ref);
  if (!m) return null;
  const [, run, path, item] = m;
  return itemHref(run, path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "", item);
}

/** Opens a figure mark's item on its run's Items tab, as the trace finds it; rejects with why
 * when it cannot. */
export function useOpenMark(source: string | undefined) {
  const client = useQueryClient();
  const router = useRouter();
  return useCallback(
    async (key: string) => {
      if (!source) return;
      const href = itemPage(await client.fetchQuery(q.trace(`${source}#${key}`)));
      if (!href) throw new Error(`item ${key} has no records to open`);
      router.push(href);
    },
    [client, router, source],
  );
}

/** What a hovered mark stands for: its item, the files holding it, and the script and commit
 * that made the figure. */
export function MarkTrace({
  source,
  mark,
  failed,
}: {
  source: string;
  mark: string | null;
  /** Why the last click could not open its item. */
  failed?: string | null;
}) {
  const trace = useQuery({ ...q.trace(`${source}#${mark}`), enabled: mark !== null });
  if (failed) return <span className="text-negative">{failed}</span>;
  if (mark === null)
    return (
      <span className="text-muted-foreground">Hover a point for its item; click to open it.</span>
    );
  if (trace.error) return <span className="text-negative">{String(trace.error)}</span>;
  const steps = trace.data?.steps ?? [];
  const item = steps.find((s) => s.what === "item");
  const script = steps.find((s) => s.what === "script");
  const run = steps.find((s) => s.what === "run");
  const made = script ?? run;
  return (
    <span className="font-mono">
      item {mark}
      {item?.rows && ` · ${Object.keys(item.rows).length} files`}
      {made && ` · ${script ? script.title : "logged by the run"}`}
      {made?.commit &&
        ` at ${made.commit.slice(0, 7)}${made.dirty ? " (uncommitted changes)" : ""}`}
    </span>
  );
}
