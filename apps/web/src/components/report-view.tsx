"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useState } from "react";

import { Help } from "@/components/help";
import { Markdown } from "@/components/markdown";
import { Part, part, partId } from "@/components/parts";
import { PdfPage } from "@/components/pdf-page";
import { QueryState } from "@/components/query-state";
import { RefLink } from "@/components/reports-view";
import { Button } from "@/components/ui/button";
import { q, reportFile, type Report } from "@/lib/api";

/** One file of reports/: Markdown rendered, a PDF or a figure as it is, and a deck or document
 * as LibreOffice prints it, or as its text when LibreOffice is not installed. */
export function ReportView() {
  const [path] = useQueryState("path", parseAsString);
  const reports = useQuery(q.reports());
  return (
    <QueryState query={reports}>
      {(all) => {
        const found = all.find((r) => r.path === path);
        return found ? (
          <Viewer report={found} />
        ) : (
          <p className="text-muted-foreground mx-auto max-w-6xl px-6 py-8 text-sm">
            No report {path ? <span className="font-mono">{path}</span> : "named"}.{" "}
            <Link href="/reports/" className="underline underline-offset-4">
              All reports
            </Link>
          </p>
        );
      }}
    </QueryState>
  );
}

function Viewer({ report: r }: { report: Report }) {
  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-8" {...part("report/header")}>
          <Link href="/reports/" className="text-muted-foreground text-xs hover:underline">
            Reports
          </Link>
          <h1 className="font-mono text-xl font-semibold tracking-tight">{r.path}</h1>
          <p className="text-muted-foreground text-sm">
            {r.ref ? (
              <>
                Exported from{" "}
                <span className="font-mono break-all">
                  <RefLink refText={r.ref} />
                </span>
                , with its trace beside it.
              </>
            ) : (
              "What this file says, as it will be read."
            )}
          </p>
          <a
            href={reportFile(r.path, true)}
            className="text-muted-foreground flex w-fit items-center gap-1 text-xs hover:underline"
          >
            <Download className="size-3" /> Download
          </a>
        </div>
      </header>
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-8">
        {r.kind === "md" && <MarkdownReport report={r} />}
        {r.kind === "pdf" && <Pages file={reportFile(r.path)} />}
        {(r.kind === "svg" || r.kind === "png") && (
          <figure className="rounded-xl border" {...part("report/figure")}>
            <figcaption className="flex items-center gap-1.5 border-b px-4 py-3 text-sm font-medium">
              {r.path.split("/").pop()}
              <Help label="How to read this figure">
                {r.ref
                  ? "A figure exported from a run, as a deck or document shows it. Its run's Figures tab shows it live, with each mark's item."
                  : "An image in reports/, as a deck or document shows it."}
              </Help>
            </figcaption>
            {/* eslint-disable-next-line @next/next/no-img-element -- a file from the API, as it is */}
            <img
              src={reportFile(r.path)}
              alt={r.ref ? `Figure exported from ${r.ref}` : r.path}
              className="max-w-full rounded-b-xl bg-white p-4"
            />
          </figure>
        )}
        {(r.kind === "pptx" || r.kind === "docx") && <Office report={r} />}
      </div>
    </>
  );
}

function MarkdownReport({ report: r }: { report: Report }) {
  const text = useQuery(q.reportOutline(r.path, r.modified));
  return (
    <QueryState query={text}>
      {([body]) => (
        <Part id="report/page" className="rounded-xl border p-6">
          <Markdown>{body}</Markdown>
        </Part>
      )}
    </QueryState>
  );
}

/** A PDF a page at a time. */
function Pages({ file }: { file: string | Uint8Array }) {
  const [asked, setPage] = useQueryState("page", parseAsInteger.withDefault(1));
  const [pages, setPages] = useState(1);
  const page = Math.min(Math.max(asked, 1), pages);
  return (
    <>
      <div className="flex items-center gap-2" {...part("report/controls")}>
        <Button
          size="sm"
          variant="ghost"
          disabled={page <= 1}
          onClick={() => void setPage(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft />
        </Button>
        <span className="font-mono text-xs tabular-nums">
          {page} / {pages}
        </span>
        <Button
          size="sm"
          variant="ghost"
          disabled={page >= pages}
          onClick={() => void setPage(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight />
        </Button>
      </div>
      <div {...part("report/page")}>
        <PdfPage file={file} page={page} onPages={setPages} />
      </div>
    </>
  );
}

/** A deck or document: drawn by LibreOffice when it is installed, else its text, saying why. */
function Office({ report: r }: { report: Report }) {
  const preview = useQuery(q.reportPreview(r.path, r.modified));
  if (preview.isPending)
    return <p className="text-muted-foreground text-sm">Drawing {r.path} with LibreOffice…</p>;
  if (preview.isSuccess) return <Pages file={preview.data} />;
  return (
    <>
      <p className="text-muted-foreground text-sm" {...part("report/note")}>
        {preview.error.message} Its text follows.
      </p>
      <Outline report={r} />
    </>
  );
}

function Outline({ report: r }: { report: Report }) {
  const outline = useQuery(q.reportOutline(r.path, r.modified));
  const unit = r.kind === "pptx" ? "Slide" : "Paragraph";
  return (
    <QueryState query={outline}>
      {(blocks) => (
        <ol className="flex flex-col gap-3">
          {blocks.map((text, i) =>
            text ? (
              <li
                key={i}
                className="rounded-xl border p-4 text-sm leading-relaxed whitespace-pre-wrap"
                {...part(partId("report/block", String(i + 1)))}
              >
                <span className="text-muted-foreground mb-1 block font-mono text-xs">
                  {unit} {i + 1}
                </span>
                {text}
              </li>
            ) : null,
          )}
        </ol>
      )}
    </QueryState>
  );
}
