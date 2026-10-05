"use client";

import { ArrowDown, ArrowUp, GitCompareArrows } from "lucide-react";
import { Help } from "@/components/help";
import { arrange, part, partId, useRules } from "@/components/parts";
import { MetricName, Term } from "@/components/term";
import { GLOSSARY, type Term as TermKey } from "@/lib/glossary";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";

import { ExperimentLink } from "@/components/experiment-link";
import { MetricValue } from "@/components/metric";
import { HostBadge, KindBadge, StatusDot } from "@/components/run-badges";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isLive, type RunSummary } from "@/lib/api";
import { ago, headline } from "@/lib/format";
import { compareHref, runHref } from "@/lib/href";

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
  help,
  about,
  id,
}: {
  label: string;
  k: SortKey;
  sort: Sort;
  onSort: (s: Sort) => void;
  className?: string;
  help?: TermKey;
  about?: string | null;
  id: string;
}) {
  const active = sort.key === k;
  return (
    <TableHead className={className} {...part(id)}>
      <button
        type="button"
        className="hover:text-foreground inline-flex items-center gap-1"
        onClick={() => onSort({ key: k, desc: active ? !sort.desc : true })}
      >
        {label}
        {active && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
      {(about || help) && (
        <span className="ml-1">
          <Help label={`What is ${label}?`}>{about ?? GLOSSARY[help!]}</Help>
        </span>
      )}
    </TableHead>
  );
}

/** A column of the table: its address names it (runs/column/<id>), so a layout can rename,
 * explain, reorder or hide it. */
type Column = {
  id: string;
  label: string;
  sort?: SortKey;
  help?: TermKey;
  head?: string;
  cell?: string;
  shown?: boolean;
  render: (r: RunSummary, selected: boolean) => React.ReactNode;
};

const KINDS = ["all", "eval", "analysis", "training"] as const;
const STATES = ["all", "live", "done", "failed"] as const;

/** A run's status, as one of the three a filter asks about. */
function state(status: string): (typeof STATES)[number] {
  if (isLive(status)) return "live";
  return ["error", "failed", "killed", "cancelled"].includes(status.toLowerCase())
    ? "failed"
    : "done";
}

/** Filters kept in the URL, so a filtered list can be reloaded and shared. */
const FILTERS = {
  q: parseAsString.withDefault(""),
  kind: parseAsStringLiteral(KINDS).withDefault("all"),
  exp: parseAsString.withDefault(""),
  state: parseAsStringLiteral(STATES).withDefault("all"),
};

/** Every run, sortable and filterable; tick two to compare them. byExperiment is off where the
 * runs are already one experiment's. */
export function RunsTable({
  runs,
  compact = false,
  byExperiment = true,
}: {
  runs: RunSummary[];
  compact?: boolean;
  byExperiment?: boolean;
}) {
  const router = useRouter();
  const [sort, setSort] = useState<Sort>({ key: "created", desc: true });
  const [f, setF] = useQueryStates(FILTERS);
  const [picked, setPicked] = useState<string[]>([]);

  const experiments = [...new Set(runs.map((r) => r.experiment).filter((x) => x != null))].sort();
  const needle = f.q.toLowerCase();
  const filtering =
    !compact && (needle || f.kind !== "all" || (byExperiment && f.exp) || f.state !== "all");
  const rows = runs
    .filter(
      (r) =>
        compact ||
        ([r.name, r.experiment, r.model, r.kind].join(" ").toLowerCase().includes(needle) &&
          (f.kind === "all" || r.kind === f.kind) &&
          (!byExperiment || !f.exp || r.experiment === f.exp) &&
          (f.state === "all" || state(r.status) === f.state)),
    )
    .sort((a, b) => {
      const [x, y] = [sortValue[sort.key](a), sortValue[sort.key](b)];
      const order = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -order : order;
    });

  const toggle = (id: string, on: boolean) =>
    setPicked((p) => (on ? [...p, id].slice(-2) : p.filter((x) => x !== id)));

  const rule = useRules();
  const col = (id: string) => partId("runs/column", id);
  const all: Column[] = [
    {
      id: "select",
      label: "Select",
      head: "w-10",
      shown: !compact,
      render: (r, selected) => (
        <Checkbox
          aria-label={`Select ${r.name}`}
          checked={selected}
          onCheckedChange={(v) => toggle(r.id, !!v)}
        />
      ),
    },
    {
      id: "run",
      label: "Run",
      sort: "name",
      cell: "max-w-72",
      render: (r) => (
        <div className="flex min-w-0 flex-col">
          <Link
            href={runHref(r.id)}
            className="truncate font-medium hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {r.name}
          </Link>
          {!byExperiment ? null : r.experiment ? (
            <ExperimentLink
              name={r.experiment}
              className="text-muted-foreground truncate text-xs"
            />
          ) : (
            <span className="text-muted-foreground truncate text-xs">no experiment</span>
          )}
        </div>
      ),
    },
    {
      id: "kind",
      label: "Kind",
      render: (r) => (
        <>
          <KindBadge kind={r.kind} /> <HostBadge host={r.host} />
        </>
      ),
    },
    {
      id: "model",
      label: "Model",
      shown: !compact,
      cell: "text-muted-foreground font-mono text-xs",
      render: (r) => r.model ?? "—",
    },
    {
      id: "headline",
      label: "Headline",
      sort: "metric",
      help: "headline",
      head: "text-right",
      cell: "text-right",
      render: (r) => {
        const m = first(r);
        return m ? (
          <div className="flex flex-col items-end">
            <MetricValue value={m[1]} err={m[2]} />
            <MetricName k={m[0]} className="text-muted-foreground text-[11px]" />
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        );
      },
    },
    {
      id: "status",
      label: "Status",
      shown: !compact,
      render: (r) => <StatusDot status={r.status} samples={r.samples} total={r.total} />,
    },
    {
      id: "created",
      label: "Created",
      sort: "created",
      cell: "text-muted-foreground text-xs whitespace-nowrap",
      render: (r) => ago(r.created),
    },
  ];
  const columns = arrange(
    all.filter((c) => c.shown !== false),
    (c) => col(c.id),
    rule,
  );

  return (
    <div className="flex flex-col gap-3">
      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          <Input
            placeholder="Search name, experiment, model…"
            aria-label="Search runs"
            value={f.q}
            onChange={(e) => void setF({ q: e.target.value || null })}
            className="h-8 w-full sm:w-56"
            {...part("runs/filter/search")}
          />
          <NativeSelect
            aria-label="Kind"
            {...part("runs/filter/kind")}
            value={f.kind}
            onChange={(e) => void setF({ kind: e.target.value as (typeof KINDS)[number] })}
          >
            <option value="all">All kinds</option>
            <option value="eval">Evals</option>
            <option value="analysis">Analyses</option>
            <option value="training">Training</option>
          </NativeSelect>
          {byExperiment && (
            <NativeSelect
              aria-label="Experiment"
              {...part("runs/filter/experiment")}
              value={f.exp}
              onChange={(e) => void setF({ exp: e.target.value || null })}
            >
              <option value="">All experiments</option>
              {experiments.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </NativeSelect>
          )}
          <NativeSelect
            aria-label="Status"
            {...part("runs/filter/status")}
            value={f.state}
            onChange={(e) => void setF({ state: e.target.value as (typeof STATES)[number] })}
          >
            <option value="all">Any status</option>
            <option value="live">Live</option>
            <option value="done">Done</option>
            <option value="failed">Failed</option>
          </NativeSelect>
          {filtering && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void setF(null)}
              {...part("runs/filter/clear")}
            >
              Clear
            </Button>
          )}
          <div className="ml-auto flex items-center gap-3">
            <span className="text-muted-foreground text-xs" {...part("runs/count")}>
              <span className="font-mono tabular-nums">{rows.length}</span>
              {rows.length !== runs.length && (
                <>
                  {" of "}
                  <span className="font-mono tabular-nums">{runs.length}</span>
                </>
              )}{" "}
              runs · {picked.length === 2 ? "2 selected" : "tick two to compare"}
            </span>
            <Button
              size="sm"
              variant={picked.length === 2 ? "default" : "outline"}
              disabled={picked.length !== 2}
              onClick={() => router.push(compareHref(picked[0], picked[1]))}
              {...part("runs/compare")}
            >
              <GitCompareArrows />
              Compare
            </Button>
          </div>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => {
              const r = rule(col(c.id));
              const label = r.label ?? c.label;
              return c.sort ? (
                <SortHeader
                  key={c.id}
                  id={col(c.id)}
                  label={label}
                  k={c.sort}
                  sort={sort}
                  onSort={setSort}
                  className={c.head}
                  help={c.help}
                  about={r.about}
                />
              ) : (
                <TableHead key={c.id} className={c.head} {...part(col(c.id))}>
                  {c.id === "select" ? (
                    <span className="sr-only">Select</span>
                  ) : r.label || r.about ? (
                    <span className="inline-flex items-center gap-1">
                      {label}
                      {r.about && <Help>{r.about}</Help>}
                    </span>
                  ) : c.id === "kind" ? (
                    <Term k="kind">Kind</Term>
                  ) : (
                    label
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const selected = picked.includes(r.id);
            return (
              <TableRow
                key={r.id}
                {...part(partId("runs/row", r.id))}
                data-state={selected ? "selected" : undefined}
                className="cursor-pointer"
                onClick={() => router.push(runHref(r.id))}
              >
                {columns.map((c) => (
                  <TableCell
                    key={c.id}
                    className={c.cell}
                    onClick={c.id === "select" ? (e) => e.stopPropagation() : undefined}
                  >
                    {c.render(r, selected)}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
          {rows.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell
                colSpan={columns.length}
                className="text-muted-foreground py-8 text-center"
              >
                No runs match these filters.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
