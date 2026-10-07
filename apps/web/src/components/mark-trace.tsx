"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { CodeLink } from "@/components/code-link";
import { part, partId } from "@/components/parts";
import { q, type Trace } from "@/lib/api";
import { itemHref } from "@/lib/href";

/** Where an item step's record sits: its run, item folder and key, from its ref. */
const ITEM = /^run:([^/#]+)\/([^#]+)#([\s\S]+)$/;

/** The Items tab with a traced item open, from the trace's item step. */
function itemPage(trace: Trace): string | null {
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

/** The code that made a figure: its derive script, else the run that logged it. */
function madeBy(trace: Trace | undefined) {
  const steps = trace?.steps ?? [];
  return steps.find((s) => s.what === "script") ?? steps.find((s) => s.what === "run");
}

/** What a hovered mark stands for: its item, the files holding it, and the script and commit
 * that made the figure; while no mark is hovered, a link to that code. */
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
  const figure = useQuery(q.trace(source)); // the figure's own trace, for its code
  const code = madeBy(figure.data)?.code;
  if (failed) return <span className="text-negative">{failed}</span>;
  if (mark === null)
    return (
      <span className="text-muted-foreground inline-flex flex-wrap items-center gap-x-2">
        Hover a point for its item; click to open it.
        {code && (
          <span {...part(partId("figures/code", source.split("/").pop() ?? source))}>
            <CodeLink code={code} short />
          </span>
        )}
      </span>
    );
  if (trace.error) return <span className="text-negative">{String(trace.error)}</span>;
  const item = trace.data?.steps.find((s) => s.what === "item");
  const made = madeBy(trace.data);
  return (
    <span className="font-mono">
      item {mark}
      {item?.rows && ` · ${Object.keys(item.rows).length} files`}
      {made && ` · ${made.what === "script" ? made.title : "logged by the run"}`}
      {made?.commit &&
        ` at ${made.commit.slice(0, 7)}${made.dirty ? " (uncommitted changes)" : ""}`}
    </span>
  );
}
