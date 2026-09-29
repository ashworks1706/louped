"use client";

import { ArrowDown, ArrowUp, GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MetricValue } from "@/components/metric";
import { KindBadge, StatusDot } from "@/components/run-badges";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { RunSummary } from "@/lib/api";
import { ago, headline, metricLabel } from "@/lib/format";

export const runHref = (id: string, tab?: string) =>
  `/run/?id=${encodeURIComponent(id)}${tab ? `&tab=${tab}` : ""}`;

type SortKey = "name" | "metric" | "created";
type Sort = { key: SortKey; desc: boolean };

const first = (r: RunSummary) => headline(r.metrics)[0];

const sortValue: Record<SortKey, (r: RunSummary) => string | number> = {
  name: (r) => r.name.toLowerCase(),
  metric: (r) => first(r)?.[1] ?? -Infinity,
  created: (r) => (r.created ? Date.parse(r.created) : 0),
};

function SortHeader({
  label,
  k,
  sort,
  onSort,
  className,
}: {
  label: string;
  k: SortKey;
  sort: Sort;
  onSort: (s: Sort) => void;
  className?: string;
}) {
  const active = sort.key === k;
  return (
    <TableHead className={className}>
      <button
        type="button"
        className="hover:text-foreground inline-flex items-center gap-1"
        onClick={() => onSort({ key: k, desc: active ? !sort.desc : true })}
      >
        {label}
        {active && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </TableHead>
  );
}

/** Every run, sortable and filterable; tick two to compare them. */
export function RunsTable({ runs, compact = false }: { runs: RunSummary[]; compact?: boolean }) {
  const router = useRouter();
  const [sort, setSort] = useState<Sort>({ key: "created", desc: true });
  const [filter, setFilter] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const needle = filter.toLowerCase();
  const rows = runs
    .filter((r) => [r.name, r.experiment, r.model, r.kind].join(" ").toLowerCase().includes(needle))
    .sort((a, b) => {
      const [x, y] = [sortValue[sort.key](a), sortValue[sort.key](b)];
      const order = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -order : order;
    });

  const toggle = (id: string, on: boolean) =>
    setPicked((p) => (on ? [...p, id].slice(-2) : p.filter((x) => x !== id)));

  return (
    <div className="flex flex-col gap-3">
      {!compact && (
        <div className="flex items-center gap-2">
          <Input
            placeholder="Filter by name, experiment, model…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="max-w-xs"
          />
          <span className="text-muted-foreground ml-auto hidden text-xs sm:inline">
            {picked.length === 2 ? "2 selected" : "Tick two runs to compare"}
          </span>
          <Button
            size="sm"
            variant={picked.length === 2 ? "default" : "outline"}
            disabled={picked.length !== 2}
            onClick={() =>
              router.push(
                `/compare/?a=${encodeURIComponent(picked[0])}&b=${encodeURIComponent(picked[1])}`,
              )
            }
          >
            <GitCompareArrows />
            Compare
          </Button>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {!compact && (
              <TableHead className="w-10">
                <span className="sr-only">Select</span>
              </TableHead>
            )}
            <SortHeader label="Run" k="name" sort={sort} onSort={setSort} />
            <TableHead>Kind</TableHead>
            {!compact && <TableHead>Model</TableHead>}
            <SortHeader
              label="Headline"
              k="metric"
              sort={sort}
              onSort={setSort}
              className="text-right"
            />
            {!compact && <TableHead>Status</TableHead>}
            <SortHeader label="Created" k="created" sort={sort} onSort={setSort} />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const m = first(r);
            const selected = picked.includes(r.id);
            return (
              <TableRow
                key={r.id}
                data-state={selected ? "selected" : undefined}
                className="cursor-pointer"
                onClick={() => router.push(runHref(r.id))}
              >
                {!compact && (
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      aria-label={`Select ${r.name}`}
                      checked={selected}
                      onCheckedChange={(v) => toggle(r.id, !!v)}
                    />
                  </TableCell>
                )}
                <TableCell className="max-w-72">
                  <div className="flex min-w-0 flex-col">
                    <Link
                      href={runHref(r.id)}
                      className="truncate font-medium hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {r.name}
                    </Link>
                    <span className="text-muted-foreground truncate text-xs">
                      {r.experiment ?? "no experiment"}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <KindBadge kind={r.kind} />
                </TableCell>
                {!compact && (
                  <TableCell className="text-muted-foreground font-mono text-xs">
                    {r.model ?? "—"}
                  </TableCell>
                )}
                <TableCell className="text-right">
                  {m ? (
                    <div className="flex flex-col items-end">
                      <MetricValue value={m[1]} err={m[2]} />
                      <span className="text-muted-foreground text-[11px]">{metricLabel(m[0])}</span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                {!compact && (
                  <TableCell>
                    <StatusDot status={r.status} samples={r.samples} total={r.total} />
                  </TableCell>
                )}
                <TableCell className="text-muted-foreground text-xs whitespace-nowrap">
                  {ago(r.created)}
                </TableCell>
              </TableRow>
            );
          })}
          {rows.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={7} className="text-muted-foreground py-8 text-center">
                No runs match “{filter}”.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
