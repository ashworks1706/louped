"use client";

import { useQuery } from "@tanstack/react-query";
import { Move3d } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { ExamplesButton } from "@/components/examples-button";
import { PartData, part, partId, useRules } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Figure } from "@/components/run-views";
import { Term } from "@/components/term";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { q, type Direction } from "@/lib/api";
import { ago } from "@/lib/format";
import { runHref } from "@/lib/href";

/** Probe with this vector already picked, on the tab named. */
function probeHref(v: Direction, tab: "reply" | "dose") {
  const p = new URLSearchParams({ vector: v.name, layer: String(v.layer), tab });
  return `/behavior/probe/?${p}`;
}

/** Saved vectors, one table per model since a vector only applies to its own model; each row
 * opens Probe to steer with it or sweep its strength. */
export function VectorsTable() {
  const vectors = useQuery(q.vectors());
  return (
    <QueryState query={vectors}>
      {(all) => {
        if (all.length === 0)
          return (
            <EmptyState
              icon={Move3d}
              title="No vectors saved"
              body="An experiment that finds a direction saves it with save_vector. The examples save one from a tiny model."
            >
              <ExamplesButton />
            </EmptyState>
          );
        const models = [...new Set(all.map((v) => v.model))].sort();
        return (
          <div className="flex flex-col gap-8">
            <PartData
              prefix="vectors/row"
              resolve={(id) => all.find((v) => partId("vectors/row", v.name) === id)}
            />
            {models.map((model) => (
              <section key={model} className="flex flex-col gap-2">
                <h2
                  className="flex items-center gap-2 text-sm font-medium"
                  {...part(partId("vectors/model", model))}
                >
                  <Term k="model">
                    <span className="font-mono">{model}</span>
                  </Term>
                </h2>
                <div className="rounded-xl border">
                  <Rows vectors={all.filter((v) => v.model === model)} />
                </div>
                {all.filter((v) => v.model === model).length > 1 && <Alike model={model} />}
              </section>
            ))}
          </div>
        );
      }}
    </QueryState>
  );
}

/** How alike a model's vectors are: a new one near 0 to the rest is new; two near 1 are one. */
function Alike({ model }: { model: string }) {
  const fig = useQuery(q.similarity(model));
  const id = partId("vectors/similar", model);
  if (useRules()(id).hidden || !fig.data) return null;
  return <Figure view={fig.data} id={id} />;
}

function Rows({ vectors }: { vectors: Direction[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead {...part(partId("vectors/column", "name"))} className="pl-4">
            Name
          </TableHead>
          <TableHead {...part(partId("vectors/column", "layer"))} className="text-right">
            <Term k="layer">Layer</Term>
          </TableHead>
          <TableHead {...part(partId("vectors/column", "method"))} className="hidden sm:table-cell">
            <Term k="method">Method</Term>
          </TableHead>
          <TableHead
            {...part(partId("vectors/column", "norm"))}
            className="hidden text-right sm:table-cell"
          >
            <Term k="norm">Norm</Term>
          </TableHead>
          <TableHead
            {...part(partId("vectors/column", "dim"))}
            className="hidden text-right md:table-cell"
          >
            <Term k="dim">Dim</Term>
          </TableHead>
          <TableHead {...part(partId("vectors/column", "source"))} className="hidden md:table-cell">
            <Term k="source">Source</Term>
          </TableHead>
          <TableHead {...part(partId("vectors/column", "use"))} className="pr-4 text-right">
            <span className="sr-only">Use</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {vectors.map((v) => (
          <TableRow key={v.name} {...part(partId("vectors/row", v.name))}>
            <TableCell className="pl-4">
              <div className="font-mono text-sm">{v.name}</div>
              <div className="text-muted-foreground max-w-sm truncate text-xs">
                {v.notes ?? `saved ${ago(v.created)}`}
              </div>
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums">{v.layer}</TableCell>
            <TableCell className="text-muted-foreground hidden text-xs sm:table-cell">
              {v.method}
            </TableCell>
            <TableCell className="hidden text-right font-mono tabular-nums sm:table-cell">
              {v.norm.toFixed(2)}
            </TableCell>
            <TableCell className="hidden text-right font-mono tabular-nums md:table-cell">
              {v.dim}
            </TableCell>
            <TableCell className="hidden md:table-cell">
              {v.run ? (
                <Link
                  href={runHref(v.run, "figures")}
                  className="text-muted-foreground hover:text-foreground text-xs underline-offset-4 hover:underline"
                >
                  run
                </Link>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell className="pr-4">
              <div className="flex justify-end gap-1.5">
                <Button asChild size="sm" variant="outline">
                  <Link href={probeHref(v, "reply")} aria-label={`Steer with ${v.name}`}>
                    Steer
                  </Link>
                </Button>
                <Button asChild size="sm" variant="ghost" className="hidden sm:inline-flex">
                  <Link href={probeHref(v, "dose")} aria-label={`Dose curve of ${v.name}`}>
                    Dose
                  </Link>
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
