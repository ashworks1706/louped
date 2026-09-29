"use client";

import { useQuery } from "@tanstack/react-query";
import { Move3d } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { runHref } from "@/lib/href";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { q } from "@/lib/api";
import { ago } from "@/lib/format";

export function VectorsTable() {
  const vectors = useQuery(q.vectors());
  return (
    <QueryState query={vectors}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={Move3d}
            title="No vectors saved"
            body="Directions from activations, with the run behind each."
            command="uv run --all-extras python experiments/refusal-direction/run.py --tiny"
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="hidden sm:table-cell">Model</TableHead>
                <TableHead className="text-right">Layer</TableHead>
                <TableHead className="hidden sm:table-cell">Method</TableHead>
                <TableHead className="text-right">Norm</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Dim</TableHead>
                <TableHead className="hidden sm:table-cell">From run</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {all.map((v) => (
                <TableRow key={v.name}>
                  <TableCell>
                    <div className="font-mono text-sm">{v.name}</div>
                    {v.notes && (
                      <div className="text-muted-foreground max-w-sm truncate text-xs">
                        {v.notes}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs sm:table-cell">
                    {v.model}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{v.layer}</TableCell>
                  <TableCell className="text-muted-foreground hidden text-xs sm:table-cell">
                    {v.method}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {v.norm.toFixed(2)}
                  </TableCell>
                  <TableCell className="hidden text-right font-mono tabular-nums sm:table-cell">
                    {v.dim}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {v.run ? (
                      <Link
                        href={runHref(v.run, "figures")}
                        className="font-mono text-xs hover:underline"
                      >
                        {v.run.slice(0, 10)}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground hidden text-right text-xs sm:table-cell">
                    {ago(v.created)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )
      }
    </QueryState>
  );
}
