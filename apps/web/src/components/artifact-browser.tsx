"use client";

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { CopyButton } from "@/components/copy-button";
import { Markdown } from "@/components/markdown";
import { EditableText } from "@/components/markdown-editor";
import { QueryState } from "@/components/query-state";
import { LinedUp } from "@/components/items-view";
import { Timeline } from "@/components/trace-view";
import { JsonTree, RecordsTable } from "@/components/record-view";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { saveArtifact, type RunDetail } from "@/lib/api";
import {
  PREVIEW_BYTES,
  artifactQuery,
  artifactUrl,
  asRecords,
  editable,
  kindOf,
  parseDelimited,
  parseJsonl,
  traceShape,
  type Row,
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
  const [filter, setFilter] = useState("");
  const groups = useMemo(
    () =>
      Map.groupBy(files, (a) =>
        a.path.includes("/") ? a.path.slice(0, a.path.lastIndexOf("/")) : "",
      ),
    [files],
  );
  // `dir/*`: every JSONL file of a folder read as one (a folder of traces, one file per request)
  const whole = file?.endsWith("/*") ? file.slice(0, -2) : null;
  const wholeFiles = whole !== null ? (groups.get(whole) ?? []).filter(isJsonl) : [];
  const picked =
    files.find((a) => a.path === file) ??
    files.find((a) => a.path === "report.md") ??
    files.find((a) => kindOf(a.path) === "markdown") ??
    files[0];
  if (!picked) return <p className="text-muted-foreground text-sm">No artifacts.</p>;
  const showWhole = whole !== null && wholeFiles.length > 1;
  const title = showWhole ? `${whole}/ · ${wholeFiles.length} files as one` : picked.path;
  const needle = filter.toLowerCase();
  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <nav
        aria-label="Artifacts"
        className="flex max-h-72 flex-col gap-3 overflow-y-auto rounded-xl border p-2 lg:sticky lg:top-4 lg:max-h-[calc(100svh-6rem)] lg:self-start lg:rounded-none lg:border-0 lg:p-0"
      >
        {files.length > FILTER_FROM && (
          <Input
            aria-label="Filter files"
            placeholder={`Filter ${files.length} files…`}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-8 shrink-0 font-mono text-xs"
          />
        )}
        {[...groups].map(([dir, items]) => {
          const shown = items.filter((a) => a.path.toLowerCase().includes(needle));
          const jsonl = items.filter(isJsonl).length;
          if (shown.length === 0) return null;
          return (
            <div key={dir} className="flex flex-col">
              {dir && (
                <span className="text-muted-foreground px-2 pb-1 font-mono text-xs">
                  {dir}/ <span className="tabular-nums">· {items.length}</span>
                </span>
              )}
              {jsonl > 1 && (
                <FileButton
                  label={`every file${dir ? ` in ${dir}/` : ""}, as one (${jsonl})`}
                  current={showWhole && whole === dir}
                  onClick={() => void setFile(`${dir}/*`)}
                />
              )}
              {shown.slice(0, needle ? undefined : LIST_LIMIT).map((a) => (
                <FileButton
                  key={a.path}
                  label={dir ? a.path.slice(dir.length + 1) : a.path}
                  bytes={a.size}
                  current={!showWhole && a.path === picked.path}
                  onClick={() => void setFile(a.path)}
                />
              ))}
              {!needle && shown.length > LIST_LIMIT && (
                <span className="text-muted-foreground px-2 py-1 text-xs">
                  {shown.length - LIST_LIMIT} more: filter to find one
                </span>
              )}
            </div>
          );
        })}
      </nav>
      <section className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <FileText className="text-muted-foreground size-4" />
          <h2 className="font-mono text-sm">{title}</h2>
          {!showWhole && <CopyButton text={picked.path} />}
          {!showWhole && (
            <Button asChild variant="outline" size="sm" className="ml-auto">
              <a href={artifactUrl(run.id, picked.path)} target="_blank" rel="noreferrer">
                <ExternalLink /> Raw
              </a>
            </Button>
          )}
        </div>
        {showWhole ? (
          <WholeFolder runId={run.id} paths={wholeFiles.map((a) => a.path)} name={whole!} />
        ) : (
          <Preview runId={run.id} artifact={picked} />
        )}
      </section>
    </div>
  );
}

/** Past this many files the list gets a filter; past LIST_LIMIT in a folder it is cut short. */
const FILTER_FROM = 12;
const LIST_LIMIT = 40;
/** A folder read as one loads at most this many files. */
const WHOLE_LIMIT = 500;

const isJsonl = (a: Artifact) => kindOf(a.path) === "jsonl";

function FileButton({
  label,
  bytes,
  current,
  onClick,
}: {
  label: string;
  bytes?: number | null;
  current: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={current ? "true" : undefined}
      className={cn(
        "hover:bg-accent flex shrink-0 items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left",
        current && "bg-accent",
      )}
    >
      <span className="truncate font-mono text-xs">{label}</span>
      {bytes !== undefined && (
        <span className="text-muted-foreground shrink-0 font-mono text-[11px] tabular-nums">
          {size(bytes)}
        </span>
      )}
    </button>
  );
}

/** Every JSONL file of a folder, its records joined, each tagged with the file it came from. */
function WholeFolder({ runId, paths, name }: { runId: string; paths: string[]; name: string }) {
  const kept = paths.slice(0, WHOLE_LIMIT);
  const queries = useQueries({ queries: kept.map((p) => artifactQuery(runId, p)) });
  const failed = queries.find((q) => q.error);
  if (failed) return <p className="text-negative text-sm">{String(failed.error)}</p>;
  const done = queries.filter((q) => q.data !== undefined).length;
  if (done < kept.length)
    return (
      <p className="text-muted-foreground text-sm">
        Reading {done} of {kept.length} files…
      </p>
    );
  const rows = queries.flatMap((q, i) =>
    parseJsonl(q.data!).rows.map((r) => ({
      ...r,
      source_file: kept[i].slice(kept[i].lastIndexOf("/") + 1),
    })),
  );
  return (
    <>
      {paths.length > WHOLE_LIMIT && (
        <p className="text-muted-foreground text-xs">
          The first {WHOLE_LIMIT} of {paths.length} files.
        </p>
      )}
      <Records rows={rows} name={`${name}.jsonl`} />
    </>
  );
}

function size(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** One of a run's files, drawn as the Artifacts tab draws it: a layout's file block or tab. */
export function RunFile({ run, path }: { run: RunDetail; path: string }) {
  const artifact = run.artifacts.find((a) => a.path === path);
  return artifact ? <Preview runId={run.id} artifact={artifact} /> : null;
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
  return (
    <QueryState query={query}>
      {(text) => <Rendered runId={runId} path={path} text={text} />}
    </QueryState>
  );
}

function Rendered({ runId, path, text }: { runId: string; path: string; text: string }) {
  const client = useQueryClient();
  const name = path.slice(path.lastIndexOf("/") + 1);
  const view = (t: string) => <View path={path} name={name} text={t} />;
  if (!editable(path)) return view(text);
  const editor = (
    <EditableText
      name={name}
      shown={text}
      preview={view}
      save={async (t) => {
        await saveArtifact(runId, path, t);
        await client.invalidateQueries({ queryKey: ["artifact", runId, path] });
        await client.invalidateQueries({ queryKey: ["run", runId] }); // its louped.edited tag
      }}
    />
  );
  return kindOf(path) === "markdown" ? (
    <article className="rounded-xl border px-6 py-5">{editor}</article>
  ) : (
    editor
  );
}

/** A text file drawn for its kind: Markdown rendered, records as a table, the rest as text. */
function View({ path, name, text }: { path: string; name: string; text: string }) {
  switch (kindOf(path)) {
    case "markdown":
      return <Markdown>{text}</Markdown>;
    case "json":
      return <JsonFile text={text} name={name} />;
    case "jsonl": {
      const { rows, bad } = parseJsonl(text);
      return (
        <>
          {bad > 0 && (
            <p className="text-negative text-xs">
              {bad} lines did not parse as JSON and are left out.
            </p>
          )}
          <Records rows={rows} name={name} />
        </>
      );
    }
    case "table":
      return (
        <RecordsTable
          rows={parseDelimited(text, path.toLowerCase().endsWith(".tsv") ? "\t" : ",")}
          name={name}
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
  if (records) return <Records rows={records} name={name} />;
  return (
    <div className="overflow-x-auto rounded-xl border p-4">
      <JsonTree value={value} />
    </div>
  );
}

/** Records as a timeline when they read as a trace (a time and a kind on every event), with the
 * table a switch away; else as a table that can line up by a column. */
function Records({ rows, name }: { rows: Row[]; name: string }) {
  const shape = useMemo(() => traceShape(rows), [rows]);
  const [view, setView] = useQueryState("view", parseAsString);
  if (!shape) return <LinedUp rows={rows} name={name} />;
  const table = view === "table";
  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Show as" className="flex w-fit rounded-md border p-0.5">
        {(["timeline", "table"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={(v === "table") === table}
            onClick={() => void setView(v === "table" ? "table" : null)}
            className={cn(
              "rounded px-2.5 py-1 text-xs capitalize",
              (v === "table") === table ? "bg-accent text-foreground" : "text-muted-foreground",
            )}
          >
            {v}
          </button>
        ))}
      </div>
      {table ? <LinedUp rows={rows} name={name} /> : <Timeline rows={rows} {...shape} />}
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
