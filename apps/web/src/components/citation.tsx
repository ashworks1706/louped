"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { q } from "@/lib/api";
import { sourceHref } from "@/lib/href";

/** [@key p4] in Markdown: a link to that page of the source, which shows on hover the source's
 * title and the passages pinned on that page. */
export function Citation({ cite, page }: { cite: string; page: number | null }) {
  const sources = useQuery(q.sources());
  const pins = useQuery(q.pins(cite));
  const source = sources.data?.find((s) => s.key === cite);
  const quotes = (pins.data ?? []).filter((p) => page == null || p.page === page);
  const label = `${cite}${page != null ? ` p${page}` : ""}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={sourceHref(cite, page ?? undefined)}
          className="bg-muted rounded px-1 py-0.5 font-mono text-[0.8em] no-underline hover:underline"
          data-cite={cite}
        >
          {label}
        </Link>
      </TooltipTrigger>
      <TooltipContent className="flex max-w-sm flex-col gap-2">
        {sources.isPending ? null : sources.isError ? (
          <span className="text-muted-foreground">
            Sources could not be read: {sources.error.message}
          </span>
        ) : source ? (
          <>
            <span className="font-medium">{source.title}</span>
            {quotes.map((p) => (
              <blockquote key={p.id} className="line-clamp-4 border-l-2 pl-2">
                {p.exact}
              </blockquote>
            ))}
            {quotes.length === 0 && (
              <span className="text-muted-foreground">Nothing pinned on this page.</span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">No source {cite} in sources/.</span>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
