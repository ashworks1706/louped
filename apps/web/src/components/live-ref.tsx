"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import Link from "next/link";
import { createContext, useContext } from "react";

import { part, partId } from "@/components/parts";
import { Figure } from "@/components/run-views";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Live } from "@/lib/api";
import { runHref } from "@/lib/href";

/** A live ref in Markdown, what is between its braces as group 1: {{run:<id> <metric>}},
 * {{run:<id> <metric> :.1%}} or {{<ref to a figure>}} (louped.reports.LIVE). */
export const LIVE = /\{\{[ \t]*((?:run|experiment):[^{}\n]*?)[ \t]*\}\}/g;

/** A live ref with no metric draws a figure, which takes a block of its own. */
export const isFigure = (text: string) => text.trim().split(/\s+/).length === 1;

/** The live refs of one Markdown text, resolved together. */
export const LiveRefs = createContext<UseQueryResult<Live[]> | null>(null);

/** A live ref: a run's metric as its value, linked to the run with the ref on hover; a figure
 * drawn; or, when it does not resolve, the ref as written, marked, with why on hover. */
export function LiveRef({ text }: { text: string }) {
  const query = useContext(LiveRefs);
  const wrote = `{{${text}}}`;
  if (!query || query.isPending)
    return (
      <span className="text-muted-foreground font-mono text-[0.85em]" title={wrote}>
        …
      </span>
    );
  const found = query.data?.find((l) => l.text === text);
  const error = query.isError
    ? `Live refs could not be read: ${query.error.message}`
    : (found?.error ?? (found ? null : "The server did not answer for it."));
  if (error || !found)
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className="border-negative text-negative rounded border px-1 font-mono text-[0.8em]"
            data-live-error={text}
            {...part(partId("live/value", text))}
          >
            {wrote}
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm">Does not resolve: {error}</TooltipContent>
      </Tooltip>
    );
  if (found.view)
    return <Figure view={found.view} id={partId("live/figure", found.ref)} source={found.ref} />;
  const run = /^run:([^/#\s]+)/.exec(found.ref)?.[1];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={run ? runHref(run) : "#"}
          className="font-mono text-[0.9em] tabular-nums underline decoration-dotted underline-offset-4 hover:decoration-solid"
          data-live={text}
          {...part(partId("live/value", text))}
        >
          {found.value}
        </Link>
      </TooltipTrigger>
      <TooltipContent className="flex max-w-sm flex-col gap-1">
        <span className="font-mono break-all">{wrote}</span>
        <span className="text-muted-foreground">
          The latest {found.metric} the run logged, read when this page opened.
        </span>
      </TooltipContent>
    </Tooltip>
  );
}
