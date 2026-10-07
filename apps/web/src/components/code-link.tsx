"use client";

import { ExternalLink } from "lucide-react";

import { CopyButton } from "@/components/copy-button";
import type { Code } from "@/lib/api";

/** The code a run or figure came from: its commit, a link to its script at that commit on the
 * forge (a copy button when the remote is elsewhere), and whether the commit is exactly what ran
 * and is pushed. Short: the 7-character sha and no copy button, for a line of text. */
export function CodeLink({ code, short = false }: { code: Code; short?: boolean }) {
  const sha = code.commit.slice(0, short ? 7 : 12);
  const what = code.path ? `${code.path} at ${sha}` : `the tree at ${sha}`;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 font-mono">
      <span title={code.commit}>{sha}</span>
      {code.url ? (
        <a
          href={code.url}
          target="_blank"
          rel="noreferrer"
          title={`Open ${what}`}
          className="text-foreground inline-flex items-center gap-1 font-sans underline underline-offset-2"
        >
          Code
          <ExternalLink className="size-3" />
        </a>
      ) : (
        !short && <CopyButton text={code.commit} label="Copy the commit" />
      )}
      {code.dirty && (
        <span
          className="text-muted-foreground font-sans"
          title="The tree had changes when it ran: the code at this commit is not exactly what ran."
        >
          uncommitted changes
        </span>
      )}
      {code.pushed === false && (
        <span
          className="text-muted-foreground font-sans"
          title="No remote branch holds this commit: push it for the link to open."
        >
          not pushed
        </span>
      )}
    </span>
  );
}
