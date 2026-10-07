"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { Part, part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { q, type Experiment, type Report } from "@/lib/api";
import { experimentHref, refRunHref, reportHref, runHref } from "@/lib/href";

/** Where a report is filed: the experiment it reports on, else its top folder, else Other. */
type Group = { key: string; experiment: string | null; title: string; reports: Report[] };

function groups(all: Report[]): Group[] {
  const found = new Map<string, Group>();
  for (const r of all) {
    const folder = r.path.includes("/") ? r.path.split("/")[0] : null;
    const experiment = r.experiment ?? null;
    const key = experiment ?? (folder ? `${folder}/` : "other");
    const title = experiment ?? (folder ? `${folder}/` : "Other");
    if (!found.has(key)) found.set(key, { key, experiment, title, reports: [] });
    found.get(key)!.reports.push(r);
  }
  // experiments first, then folders, then Other
  const rank = (g: Group) => (g.experiment ? 0 : g.key === "other" ? 2 : 1);
  return [...found.values()].sort((a, b) => rank(a) - rank(b) || a.key.localeCompare(b.key));
}

/** The files in reports/, by the experiment each reports on: write-ups, decks, documents, PDFs
 * and exported figures. */
export function ReportsView() {
  const reports = useQuery(q.reports());
  const experiments = useQuery(q.experiments());
  const axis = new Map((experiments.data ?? []).map((e) => [e.name, e.axis]));
  return (
    <QueryState query={reports}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No reports yet"
            body="Write-ups, decks and documents your agent writes into reports/, and figures exported from a run's Figures tab."
            action={{ href: "/runs/", label: "Runs" }}
          />
        ) : (
          <section className="flex flex-col gap-3">
            <h2
              className="flex items-center gap-1.5 text-sm font-medium"
              {...part("reports/heading")}
            >
              <span>
                <span className="font-mono tabular-nums">{all.length}</span>{" "}
                {all.length === 1 ? "file" : "files"}
              </span>
              <Help label="How reports are grouped">
                By the experiment each reports on: an experiment: line in a Markdown file&apos;s
                front matter, else its folder in reports/ when an experiment has that name, else the
                one experiment all its refs point to. The rest are grouped by folder.
              </Help>
            </h2>
            <Part id="reports/table" className="flex flex-col gap-6">
              {groups(all).map((g) => (
                <ReportGroup key={g.key} group={g} axis={axis} />
              ))}
            </Part>
          </section>
        )
      }
    </QueryState>
  );
}

function ReportGroup({ group: g, axis }: { group: Group; axis: Map<string, Experiment["axis"]> }) {
  const at = g.experiment ? axis.get(g.experiment) : undefined;
  return (
    <section className="flex flex-col gap-1" {...part(partId("reports/group", g.key))}>
      <h3 className="flex items-baseline gap-2 text-sm font-medium">
        {g.experiment && at ? (
          <Link
            href={experimentHref(g.experiment, at)}
            className="font-mono underline-offset-4 hover:underline"
          >
            {g.title}
          </Link>
        ) : (
          <span className={g.key === "other" ? undefined : "font-mono"}>{g.title}</span>
        )}
        <span className="text-muted-foreground font-mono text-xs tabular-nums">
          {g.reports.length}
        </span>
      </h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>File</TableHead>
            <TableHead className="w-16">Kind</TableHead>
            <TableHead className="w-28">Changed</TableHead>
            <TableHead className="w-64">Cites</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {g.reports.map((r) => (
            <TableRow key={r.path} {...part(partId("reports/report", r.path))}>
              <TableCell className="max-w-md break-all">
                <Link
                  href={reportHref(r.path)}
                  className="font-mono text-xs underline-offset-4 hover:underline"
                  title={r.ref ? `Exported from ${r.ref}` : undefined}
                >
                  {r.path}
                </Link>
              </TableCell>
              <TableCell className="font-mono text-xs">{r.kind}</TableCell>
              <TableCell
                className="text-muted-foreground font-mono text-xs tabular-nums"
                title={r.modified}
              >
                {r.modified.slice(0, 10)}
              </TableCell>
              <TableCell className="font-mono text-xs">
                <CitedRuns runs={r.runs ?? []} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

/** The runs a report cites: the first two linked, then how many more. */
function CitedRuns({ runs }: { runs: string[] }) {
  if (runs.length === 0) return <span className="text-muted-foreground">none</span>;
  return (
    <span className="flex flex-wrap items-baseline gap-x-2" title={runs.join("\n")}>
      {runs.slice(0, 2).map((id) => (
        <Link key={id} href={runHref(id)} className="underline-offset-4 hover:underline">
          {id.slice(0, 10)}
        </Link>
      ))}
      {runs.length > 2 && (
        <span className="text-muted-foreground tabular-nums">+{runs.length - 2}</span>
      )}
    </span>
  );
}

/** The reports on one experiment, for its page. */
export function ExperimentReports({ name }: { name: string }) {
  const reports = useQuery(q.reports());
  return (
    <QueryState query={reports} rows={2}>
      {(all) => {
        const own = all.filter((r) => r.experiment === name);
        return own.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            None yet. A file in <span className="font-mono">reports/{name}/</span>, one whose front
            matter says <span className="font-mono">experiment: {name}</span>, or one citing only
            its runs shows here.{" "}
            <Link href="/reports/" className="underline underline-offset-4">
              All reports
            </Link>
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {own.map((r) => (
              <li
                key={r.path}
                className="flex items-baseline justify-between gap-3 text-xs"
                {...part(partId("experiment/report", r.path))}
              >
                <Link
                  href={reportHref(r.path)}
                  className="min-w-0 font-mono break-all underline-offset-4 hover:underline"
                >
                  {r.path}
                </Link>
                <span className="text-muted-foreground shrink-0 font-mono tabular-nums">
                  {r.kind} · {r.modified.slice(0, 10)}
                </span>
              </li>
            ))}
          </ul>
        );
      }}
    </QueryState>
  );
}

/** A ref, linked to its run's figures when it is on a run. */
export function RefLink({ refText }: { refText: string }) {
  const href = refRunHref(refText);
  return href ? (
    <Link href={href} className="underline-offset-4 hover:underline">
      {refText}
    </Link>
  ) : (
    <>{refText}</>
  );
}
