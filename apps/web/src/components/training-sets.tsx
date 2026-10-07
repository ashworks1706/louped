"use client";

import { useQuery } from "@tanstack/react-query";
import { Database, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { parseAsString, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { arrange, part, partId, PartData, useRules } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Term } from "@/components/term";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { q, type Pair, type TrainingSet } from "@/lib/api";
import { pct } from "@/lib/format";
import { GLOSSARY } from "@/lib/glossary";
import { runHref } from "@/lib/href";
import { cn } from "@/lib/utils";

type Flag = Pair["flags"][number];
const FLAGS: Flag[] = ["chosen_in_prompt", "length_only"];

const fileName = (path: string) => path.split("/").slice(-2).join("/");

/** Every training set louped knows, with its flags; one opens below with its pairs. */
export function TrainingSets() {
  const sets = useQuery(q.trainingSets());
  const [open, setOpen] = useQueryState("set", parseAsString);
  return (
    <QueryState query={sets}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={Database}
            title="No training sets"
            body="A training config names its dataset (a YAML file in an experiment that starts # louped train sft or dpo). Launch one, or build a set with louped data."
            action={{ href: "/launch/", label: "Open Launch" }}
          />
        ) : (
          <div className="flex flex-col gap-8">
            <SetsTable sets={all} open={open} onOpen={(p) => void setOpen(p)} />
            {open && <OpenSet path={open} />}
          </div>
        )
      }
    </QueryState>
  );
}

function SetsTable({
  sets,
  open,
  onOpen,
}: {
  sets: TrainingSet[];
  open: string | null;
  onOpen: (path: string) => void;
}) {
  const rule = useRules();
  const col = (id: string) => partId("sets/column", id);
  const columns = arrange(
    [
      { id: "set", label: "Set", head: "", cell: "font-mono text-xs" },
      { id: "format", label: "Format", head: "", cell: "font-mono text-xs" },
      { id: "rows", label: "Rows", head: "text-right", cell: "text-right font-mono" },
      ...FLAGS.map((f) => ({ id: f, label: f, head: "text-right", cell: "text-right font-mono" })),
      { id: "used", label: "Used by", head: "", cell: "text-xs" },
    ],
    (c) => col(c.id),
    rule,
  );
  const value = (s: TrainingSet, id: string): React.ReactNode => {
    if (id === "set")
      return (
        <span className="inline-flex items-center gap-1.5" title={s.path}>
          {s.warnings.length > 0 && <TriangleAlert className="text-negative size-3.5" />}
          {fileName(s.path)}
        </span>
      );
    if (id === "format")
      return s.error ? <span className="text-negative">{s.error}</span> : s.format;
    if (id === "rows") return s.error ? "—" : s.rows;
    if (id === "used")
      return (
        <span className="text-muted-foreground">
          {[...s.configs, ...s.runs].join(" · ") || "data/"}
        </span>
      );
    const n = s.counts[id];
    if (n == null) return "—";
    return (
      <span className={cn(s.rows && n / s.rows >= 0.2 && "text-negative")}>
        {n} <span className="text-muted-foreground text-xs">{pct(s.rows ? n / s.rows : null)}</span>
      </span>
    );
  };
  return (
    <div className="rounded-xl border">
      <PartData
        prefix="sets/row"
        resolve={(id) => sets.find((s) => partId("sets/row", s.path) === id) ?? null}
      />
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c) => {
              const r = rule(col(c.id));
              const term = c.id === "chosen_in_prompt" || c.id === "length_only";
              return (
                <TableHead key={c.id} className={c.head} {...part(col(c.id))}>
                  <span className="inline-flex items-center gap-1">
                    {r.label ?? c.label}
                    {(r.about || term) && <Help>{r.about ?? GLOSSARY[c.id as Flag]}</Help>}
                  </span>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sets.map((s) => (
            <TableRow
              key={s.path}
              className={cn(!s.error && "cursor-pointer")}
              data-state={open === s.path ? "selected" : undefined}
              onClick={() => !s.error && onOpen(s.path)}
              {...part(partId("sets/row", s.path))}
            >
              {columns.map((c) => (
                <TableCell key={c.id} className={c.cell}>
                  {value(s, c.id)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** One set: what its flags say, its counts (each a filter), its labels and its pairs. */
function OpenSet({ path }: { path: string }) {
  const found = useQuery(q.trainingSet(path));
  const [flag, setFlag] = useQueryState("flag", parseAsString);
  const rule = useRules();
  const sets = useQuery(q.trainingSets());
  const set = sets.data?.find((s) => s.path === path);
  return (
    <QueryState query={found}>
      {({ report, shown }) => {
        const pairs = report.pairs.filter((p) => !flag || p.flags.includes(flag as Flag));
        return (
          <section className="flex flex-col gap-4">
            <PartData
              prefix="set/pair"
              resolve={(id) => report.pairs.find((p) => partId("set/pair", String(p.index)) === id)}
            />
            <h2 className="font-mono text-sm font-medium" title={path} {...part("set/title")}>
              {fileName(path)}
            </h2>
            {report.warnings.length > 0 && (
              <ul
                className="border-negative/50 text-negative flex flex-col gap-1 rounded-xl border p-4 text-sm"
                {...part("set/warnings")}
              >
                {report.warnings.map((w) => (
                  <li key={w} className="flex items-start gap-2">
                    <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                    {w}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="text-muted-foreground mr-2 text-xs"
                {...part(partId("set/stat", "rows"))}
              >
                <span className="text-foreground font-mono">{report.rows}</span>{" "}
                {report.format === "dpo" ? "pairs" : "examples"}
              </span>
              {Object.entries(report.counts).map(([f, n]) => {
                const id = partId("set/stat", f);
                const r = rule(id);
                if (r.hidden) return null;
                const active = flag === f;
                return (
                  <span key={f} className="inline-flex items-center gap-1" {...part(id)}>
                    <Button
                      size="sm"
                      variant={active ? "default" : "outline"}
                      onClick={() => void setFlag(active ? null : f)}
                      title={`Show only pairs flagged ${f}`}
                    >
                      {r.label ?? f}
                      <span className="font-mono text-xs tabular-nums opacity-70">
                        {n} · {pct(report.rows ? n / report.rows : null)}
                      </span>
                    </Button>
                    <Help label={`What is ${f}?`}>{r.about ?? GLOSSARY[f as Flag]}</Help>
                  </span>
                );
              })}
            </div>
            <div
              className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs"
              {...part("set/labels")}
            >
              <Term k="provenance">Label</Term>
              {Object.entries(report.labels).map(([label, n]) => (
                <span key={label}>
                  <span className="text-foreground">{label}</span>{" "}
                  <span className="font-mono">{n}</span>
                </span>
              ))}
            </div>
            {set && (set.configs.length > 0 || set.runs.length > 0) && (
              <div
                className="text-muted-foreground flex flex-wrap gap-x-3 text-xs"
                {...part("set/used")}
              >
                Used by
                {set.configs.map((c) => (
                  <span key={c} className="font-mono">
                    {c}
                  </span>
                ))}
                {set.runs.map((r) => (
                  <Link
                    key={r}
                    href={runHref(r)}
                    className="hover:text-foreground font-mono underline"
                  >
                    {r}
                  </Link>
                ))}
              </div>
            )}
            <span className="text-muted-foreground text-xs" {...part("set/count")}>
              {pairs.length} shown
              {shown < report.rows && ` · the first ${shown} of ${report.rows}, flagged ones first`}
            </span>
            {pairs.map((p) => (
              <PairCard key={p.index} pair={p} />
            ))}
          </section>
        );
      }}
    </QueryState>
  );
}

function PairCard({ pair }: { pair: Pair }) {
  const reply = (title: string, text: string) => (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-muted-foreground text-xs">{title}</span>
      <p className="bg-muted/40 rounded-md p-3 text-sm whitespace-pre-wrap">{text}</p>
    </div>
  );
  return (
    <article
      className="flex flex-col gap-3 rounded-xl border p-4"
      {...part(partId("set/pair", String(pair.index)))}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground font-mono text-xs">#{pair.index}</span>
        {pair.flags.map((f) => (
          <Badge key={f} className="border-negative/50 text-negative">
            {f}
          </Badge>
        ))}
        <span className="text-muted-foreground ml-auto text-xs">{pair.label}</span>
      </header>
      <ol className="text-muted-foreground flex max-h-48 flex-col gap-1 overflow-y-auto text-xs">
        {pair.prompt.map((m, i) => (
          <li key={i} className="whitespace-pre-wrap">
            <span className="font-mono">{String(m.role ?? "?")}</span> {text(m.content)}
          </li>
        ))}
      </ol>
      <div className={cn("grid gap-3", pair.rejected != null && "sm:grid-cols-2")}>
        {reply(pair.rejected != null ? "Chosen" : "Completion", pair.chosen)}
        {pair.rejected != null && reply("Rejected", pair.rejected)}
      </div>
    </article>
  );
}

/** A wire message's content as text: a string, or the text parts of a content array. */
function text(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content))
    return content
      .map((c) => (c && typeof c === "object" && "text" in c ? String(c.text) : ""))
      .join(" ");
  return "";
}
