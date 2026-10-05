"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
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
import { q } from "@/lib/api";
import { reportHref } from "@/lib/href";

/** The files in reports/: write-ups, decks, documents, PDFs and exported figures. */
export function ReportsView() {
  const reports = useQuery(q.reports());
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
            <h2 className="text-sm font-medium" {...part("reports/heading")}>
              <span className="font-mono tabular-nums">{all.length}</span>{" "}
              {all.length === 1 ? "file" : "files"}
            </h2>
            <Part id="reports/table">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>File</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead className="text-right">Size</TableHead>
                    <TableHead>Changed</TableHead>
                    <TableHead>Exported from</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {all.map((r) => (
                    <TableRow key={r.path} {...part(partId("reports/report", r.path))}>
                      <TableCell className="max-w-md">
                        <Link
                          href={reportHref(r.path)}
                          className="font-mono text-xs underline-offset-4 hover:underline"
                        >
                          {r.path}
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{r.kind}</TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {size(r.size)}
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {r.modified.slice(0, 16).replace("T", " ")}
                      </TableCell>
                      <TableCell className="text-muted-foreground max-w-64 truncate font-mono text-xs">
                        {r.ref ?? ""}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Part>
          </section>
        )
      }
    </QueryState>
  );
}

function size(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
