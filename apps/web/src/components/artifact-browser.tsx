"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { useMemo } from "react";

import { CopyButton } from "@/components/copy-button";
import { Markdown } from "@/components/markdown";
import { QueryState } from "@/components/query-state";
import { LinedUp } from "@/components/items-view";
import { JsonTree, RecordsTable } from "@/components/record-view";
import { Button } from "@/components/ui/button";
import type { RunDetail } from "@/lib/api";
import {
  PREVIEW_BYTES,
  artifactQuery,
  artifactUrl,
  asRecords,
  kindOf,
  parseDelimited,
  parseJsonl,
} from "@/lib/artifacts";
import { cn } from "@/lib/utils";

type Artifact = RunDetail["artifacts"][number];

/** A run's files: a list by folder beside a preview made for each type. The open file is in the
 * URL, so a link reaches it. Figures are left to the Figures tab. */
export function ArtifactBrowser({ run }: { run: RunDetail }) {
  const files = useMemo(
    () => run.artifacts.filter((a) => !a.path.startsWith("views/")),
    [run.artifacts],
  );
  const [file, setFile] = useQueryState("file", parseAsString);
  const picked =
    files.find((a) => a.path === file) ??
    files.find((a) => a.path === "report.md") ??
    files.find((a) => kindOf(a.path) === "markdown") ??
    files[0];
  if (!picked) return <p className="text-muted-foreground text-sm">No artifacts.</p>;
  const groups = Map.groupBy(files, (a) =>
    a.path.includes("/") ? a.path.slice(0, a.path.lastIndexOf("/")) : "",
  );
  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <nav aria-label="Artifacts" className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start">
        {[...groups].map(([dir, items]) => (
          <div key={dir} className="flex flex-col">
            {dir && (
              <span className="text-muted-foreground px-2 pb-1 font-mono text-xs">{dir}/</span>
            )}
            {items.map((a) => (
              <button
                key={a.path}
                onClick={() => void setFile(a.path)}
                aria-current={a.path === picked.path ? "true" : undefined}
                className={cn(
                  "hover:bg-accent flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left",
                  a.path === picked.path && "bg-accent",
                )}
              >
                <span className="truncate font-mono text-xs">
                  {dir ? a.path.slice(dir.length + 1) : a.path}
                </span>
                <span className="text-muted-foreground shrink-0 font-mono text-[11px] tabular-nums">
                  {size(a.size)}
                </span>
              </button>
            ))}
          </div>
        ))}
      </nav>
      <section className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <FileText className="text-muted-foreground size-4" />
          <h2 className="font-mono text-sm">{picked.path}</h2>
          <CopyButton text={picked.path} />
          <Button asChild variant="outline" size="sm" className="ml-auto">
            <a href={artifactUrl(run.id, picked.path)} target="_blank" rel="noreferrer">
              <ExternalLink /> Raw
            </a>
          </Button>
        </div>
        <Preview runId={run.id} artifact={picked} />
      </section>
    </div>
  );
}

function size(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function Preview({ runId, artifact }: { runId: string; artifact: Artifact }) {
  const kind = kindOf(artifact.path);
  if (kind === "image")
    return (
      // eslint-disable-next-line @next/next/no-img-element -- a run's own file, served by the API
      <img
        src={artifactUrl(runId, artifact.path)}
        alt={artifact.path}
        className="bg-background max-w-full rounded-xl border"
      />
    );
  if (kind === "other" || (artifact.size ?? 0) > PREVIEW_BYTES)
    return (
      <p className="text-muted-foreground text-sm">
        {kind === "other" ? "No preview for this type." : "Too large to preview here."} Open it with
        Raw.
      </p>
    );
  return <TextPreview runId={runId} path={artifact.path} />;
}

function TextPreview({ runId, path }: { runId: string; path: string }) {
  const query = useQuery(artifactQuery(runId, path));
  return <QueryState query={query}>{(text) => <Rendered path={path} text={text} />}</QueryState>;
}

function Rendered({ path, text }: { path: string; text: string }) {
  switch (kindOf(path)) {
    case "markdown":
      return (
        <article className="rounded-xl border px-6 py-5">
          <Markdown>{text}</Markdown>
        </article>
      );
    case "json":
      return <JsonFile text={text} name={path.slice(path.lastIndexOf("/") + 1)} />;
    case "jsonl": {
      const { rows, bad } = parseJsonl(text);
      return (
        <>
          {bad > 0 && (
            <p className="text-negative text-xs">
              {bad} lines did not parse as JSON and are left out.
            </p>
          )}
          <LinedUp rows={rows} name={path.slice(path.lastIndexOf("/") + 1)} />
        </>
      );
    }
    case "table":
      return (
        <RecordsTable
          rows={parseDelimited(text, path.toLowerCase().endsWith(".tsv") ? "\t" : ",")}
          name={path.slice(path.lastIndexOf("/") + 1)}
        />
      );
    default:
      return <Pre>{text}</Pre>;
  }
}

function JsonFile({ text, name }: { text: string; name: string }) {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (e) {
    return (
      <>
        <p className="text-negative text-xs">Not valid JSON: {(e as Error).message}</p>
        <Pre>{text}</Pre>
      </>
    );
  }
  const records = asRecords(value);
  if (records) return <LinedUp rows={records} name={name} />;
  return (
    <div className="overflow-x-auto rounded-xl border p-4">
      <JsonTree value={value} />
    </div>
  );
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="bg-muted/40 max-h-[70svh] overflow-auto rounded-xl border p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap">
      {children}
    </pre>
  );
}
