"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Plus, Rocket, Trophy } from "lucide-react";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { Part, part, partId, PartData } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { MetricName, Term } from "@/components/term";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  addBenchmark,
  isSnapshot,
  q,
  type BenchmarkRequest,
  type BenchmarkRow,
  type SpeedRow,
} from "@/lib/api";
import { ago, num } from "@/lib/format";
import { runHref } from "@/lib/href";
import { cn } from "@/lib/utils";

const NUM = "text-right font-mono tabular-nums";
const launchHref = (task: string) => `/launch/?id=eval&task=${encodeURIComponent(task)}`;

/** Every eval task with its runs as a leaderboard; inspect_evals' tasks without runs show when a
 * search finds them. */
export function EvalBenchmarks() {
  const [s, set] = useQueryStates({ q: parseAsString, task: parseAsString });
  const rows = useQuery(q.benchmarks());
  const [adding, setAdding] = useState(false);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="search"
          value={s.q ?? ""}
          onChange={(e) => void set({ q: e.target.value || null })}
          placeholder="Search tasks: gsm8k, honesty, coding…"
          aria-label="Search eval tasks"
          className="max-w-md"
          {...part("benchmarks/search")}
        />
        {!isSnapshot() && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setAdding(true)}
            {...part("benchmarks/add")}
          >
            <Plus /> Hub dataset as a benchmark
          </Button>
        )}
      </div>
      <QueryState query={rows}>
        {(all) => <Tasks rows={all} search={s.q} onOpen={(task) => void set({ task })} />}
      </QueryState>
      <Sheet open={s.task !== null} onOpenChange={(o) => !o && void set({ task: null })}>
        <SheetContent className="sm:max-w-3xl">
          {s.task !== null && <Board task={s.task} />}
        </SheetContent>
      </Sheet>
      <AddBenchmark open={adding} onOpenChange={setAdding} onAdded={(task) => void set({ task })} />
    </div>
  );
}

function Tasks({
  rows,
  search,
  onOpen,
}: {
  rows: BenchmarkRow[];
  search: string | null;
  onOpen: (task: string) => void;
}) {
  const word = search?.trim().toLowerCase();
  const shown = word
    ? rows.filter((r) =>
        [r.task.task, r.task.title, r.task.group, r.task.about ?? ""]
          .join(" ")
          .toLowerCase()
          .includes(word),
      )
    : rows.filter((r) => r.runs > 0 || r.task.source !== "inspect_evals");
  const hidden = word ? 0 : rows.length - shown.length;
  const anyRuns = rows.some((r) => r.runs > 0);
  const col = (id: string) => partId("benchmarks/column", id);
  return (
    <div className="flex flex-col gap-3">
      {!anyRuns && !word && (
        <EmptyState
          icon={Trophy}
          title="No eval has run yet"
          body="Each eval task's finished runs show here, best score first. Launch one: any task below, or an inspect_evals benchmark."
          action={{ href: "/launch/?id=eval", label: "Launch an eval" }}
        />
      )}
      {shown.length > 0 && (
        <div className="overflow-x-auto rounded-xl border">
          <PartData
            prefix="benchmarks/task"
            resolve={(id) =>
              rows.find((r) => partId("benchmarks/task", r.task.task) === id) ?? null
            }
          />
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead {...part(col("task"))}>Task</TableHead>
                <TableHead className="hidden sm:table-cell" {...part(col("group"))}>
                  Group
                </TableHead>
                <TableHead className="text-right" {...part(col("runs"))}>
                  <Term k="benchmarkRuns">Runs</Term>
                </TableHead>
                <TableHead className="text-right" {...part(col("best"))}>
                  <Term k="benchmarkScore">Best</Term>
                </TableHead>
                <TableHead {...part(col("model"))}>Model</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.slice(0, 200).map((r) => (
                <TableRow
                  key={r.task.task}
                  className="cursor-pointer"
                  tabIndex={0}
                  onClick={() => onOpen(r.task.task)}
                  onKeyDown={(e) => e.key === "Enter" && onOpen(r.task.task)}
                  {...part(partId("benchmarks/task", r.task.task))}
                >
                  <TableCell className="max-w-md">
                    <div className="flex flex-wrap items-center gap-1.5 text-sm">
                      {r.task.title}
                      {r.task.source === "benchmark" && <Badge>Hub</Badge>}
                      {r.task.source === "project" && <Badge>project</Badge>}
                    </div>
                    <p className="text-muted-foreground truncate font-mono text-xs">
                      {r.task.task}
                    </p>
                  </TableCell>
                  <TableCell className="text-muted-foreground hidden text-xs sm:table-cell">
                    {r.task.group}
                  </TableCell>
                  <TableCell className={NUM}>{r.runs || "—"}</TableCell>
                  <TableCell className={NUM}>{r.best ? num(r.best.score) : "—"}</TableCell>
                  <TableCell className="text-muted-foreground max-w-48 truncate font-mono text-xs">
                    {r.best?.model ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {word && shown.length === 0 && (
        <p className="text-muted-foreground text-sm">No eval task matches.</p>
      )}
      {(hidden > 0 || shown.length > 200) && (
        <p className="text-muted-foreground text-xs" {...part("benchmarks/more")}>
          {hidden > 0
            ? `inspect_evals tasks with no runs yet: ${hidden}. Search to find one.`
            : `The first 200 of ${shown.length}: search to narrow them.`}
        </p>
      )}
    </div>
  );
}

/** One task's leaderboard: its finished runs, best score first. */
function Board({ task }: { task: string }) {
  const board = useQuery(q.leaderboard(task));
  const t = board.data?.task;
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex flex-col gap-1 pr-8">
        <SheetTitle className="font-medium" {...part("benchmarks/board/title")}>
          {t?.title ?? task}
        </SheetTitle>
        <SheetDescription className="text-muted-foreground font-mono text-xs">
          {task}
        </SheetDescription>
      </div>
      <QueryState query={board} rows={4}>
        {(b) => (
          <>
            {!isSnapshot() && (
              <div {...part("benchmarks/board/launch")}>
                <Button asChild size="sm">
                  <Link href={launchHref(b.task?.task ?? task)}>
                    <Rocket /> Launch
                  </Link>
                </Button>
              </div>
            )}
            {b.task?.about && (
              <p className="text-muted-foreground text-sm" {...part("benchmarks/board/about")}>
                {b.task.about}
              </p>
            )}
            {b.spec && (
              <dl
                className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm"
                {...part("benchmarks/board/spec")}
              >
                {(
                  [
                    ["Dataset", b.spec.dataset],
                    ["Config", b.spec.config ?? "—"],
                    [
                      <Term key="s" k="split">
                        Split
                      </Term>,
                      b.spec.split,
                    ],
                    [<Term key="f" k="fieldMapping">Fields</Term>,
                      `${b.spec.input} → ${b.spec.target}${b.spec.choices ? ` (choices: ${b.spec.choices})` : ""}`], // prettier-ignore
                    [
                      <Term key="c" k="benchmarkScorer">
                        Scorer
                      </Term>,
                      b.spec.scorer,
                    ],
                  ] as [React.ReactNode, string][]
                ).map(([label, value], i) => (
                  <div key={i} className="contents">
                    <dt className="text-muted-foreground text-xs">{label}</dt>
                    <dd className="font-mono text-xs">{value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {b.entries.length === 0 ? (
              <p className="text-muted-foreground text-sm" {...part("benchmarks/board/empty")}>
                No finished run of this task yet. Launch it on a model to start its leaderboard.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-xl border">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead
                        className="text-right"
                        {...part(partId("benchmarks/entry-column", "rank"))}
                      >
                        #
                      </TableHead>
                      <TableHead {...part(partId("benchmarks/entry-column", "model"))}>
                        Model
                      </TableHead>
                      <TableHead
                        className="text-right"
                        {...part(partId("benchmarks/entry-column", "score"))}
                      >
                        <Term k="benchmarkScore">Score</Term>
                      </TableHead>
                      <TableHead
                        className="text-right"
                        {...part(partId("benchmarks/entry-column", "samples"))}
                      >
                        Samples
                      </TableHead>
                      <TableHead {...part(partId("benchmarks/entry-column", "date"))}>
                        Run
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {b.entries.map((e, i) => (
                      <TableRow key={e.run} {...part(partId("benchmarks/entry", e.run))}>
                        <TableCell className={NUM}>{i + 1}</TableCell>
                        <TableCell className="max-w-56 truncate font-mono text-xs">
                          {e.model ?? "—"}
                        </TableCell>
                        <TableCell className={NUM}>
                          <span className="inline-flex flex-col items-end">
                            {num(e.score)}
                            {e.metric && (
                              <MetricName
                                k={e.metric}
                                className="text-muted-foreground font-sans text-[11px]"
                              />
                            )}
                          </span>
                        </TableCell>
                        <TableCell className={NUM}>{e.samples ?? "—"}</TableCell>
                        <TableCell className="text-xs">
                          <Link
                            href={runHref(e.run)}
                            className="underline-offset-4 hover:underline"
                          >
                            {ago(e.created)}
                          </Link>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </>
        )}
      </QueryState>
    </div>
  );
}

type Field = { key: keyof BenchmarkRequest; label: string; hint: string; required?: boolean };
const FIELDS: Field[] = [
  { key: "name", label: "Name", hint: "gsm8k: lowercase, digits, - and _", required: true },
  { key: "dataset", label: "Dataset", hint: "openai/gsm8k", required: true },
  { key: "config", label: "Config", hint: "main; empty when it has one" },
  { key: "split", label: "Split", hint: "test", required: true },
  { key: "input", label: "Input field", hint: "question", required: true },
  { key: "target", label: "Target field", hint: "answer", required: true },
  { key: "choices", label: "Choices field", hint: "for multiple choice only" },
];

/** A Hub dataset made a benchmark: the fields it maps, checked against the dataset. */
function AddBenchmark({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: (task: string) => void;
}) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: addBenchmark,
    meta: { action: "Add benchmark" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["benchmarks"] });
      void client.invalidateQueries({ queryKey: ["eval-tasks"] });
      onOpenChange(false);
      onAdded(done.benchmark.task.task);
      toast(`Added ${done.benchmark.task.task}`, {
        description: done.checked ? "Its fields are in the dataset." : done.note,
      });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">Hub dataset as a benchmark</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Each row of the split is a sample. louped checks the fields against the dataset, keeps
            the mapping in louped.toml and lists it as the eval task louped/&lt;name&gt;.
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          {...part("benchmarks/form")}
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            const value = (k: string) => String(data.get(k) ?? "").trim() || null;
            save.mutate({
              name: value("name") ?? "",
              dataset: value("dataset") ?? "",
              config: value("config"),
              split: value("split") ?? "test",
              input: value("input") ?? "",
              target: value("target") ?? "",
              choices: value("choices"),
              scorer: (value("scorer") ?? "match") as BenchmarkRequest["scorer"],
            });
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map((f) => (
              <Part
                key={f.key}
                id={partId("benchmarks/form", f.key)}
                className="flex flex-col gap-1"
              >
                <label htmlFor={`bench-${f.key}`} className="text-muted-foreground text-xs">
                  {f.key === "input" || f.key === "target" || f.key === "choices" ? (
                    <Term k="fieldMapping">{f.label}</Term>
                  ) : (
                    f.label
                  )}
                </label>
                <Input
                  id={`bench-${f.key}`}
                  name={f.key}
                  placeholder={f.hint}
                  required={f.required}
                  defaultValue={f.key === "split" ? "test" : undefined}
                  className="font-mono text-xs"
                />
              </Part>
            ))}
            <Part id={partId("benchmarks/form", "scorer")} className="flex flex-col gap-1">
              <label htmlFor="bench-scorer" className="text-muted-foreground text-xs">
                <Term k="benchmarkScorer">Scorer</Term>
              </label>
              <NativeSelect
                id="bench-scorer"
                name="scorer"
                defaultValue="match"
                className="text-xs"
              >
                <option value="match">match</option>
                <option value="choice">choice</option>
                <option value="judge">judge</option>
              </NativeSelect>
            </Part>
          </div>
          <Button type="submit" size="sm" className="self-end" disabled={save.isPending}>
            {save.isPending ? "Checking" : "Add"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const SHOWS = ["newest", "best"] as const;

/** Speed benchmarks (louped bench runs) by model and weight format: newest first, or each
 * model's fastest. */
export function SpeedBenchmarks() {
  const [s, set] = useQueryStates({ show: parseAsStringLiteral(SHOWS).withDefault("newest") });
  const rows = useQuery(q.speed());
  const col = (id: string) => partId("benchmarks/speed-column", id);
  return (
    <QueryState query={rows}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No speed benchmark yet"
            body="louped bench measures throughput, prefill and memory of a model in each weight format. Launch one; each run adds its settings here."
            action={{ href: "/launch/?id=bench", label: "Launch louped bench" }}
          />
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-1" role="group" aria-label="Show">
              {SHOWS.map((v) => (
                <Button
                  key={v}
                  size="sm"
                  variant={s.show === v ? "outline" : "ghost"}
                  aria-pressed={s.show === v}
                  onClick={() => void set({ show: v })}
                  {...part(partId("benchmarks/show", v))}
                >
                  {v === "newest" ? "Newest" : "Best per model"}
                </Button>
              ))}
            </div>
            <div className="overflow-x-auto rounded-xl border">
              <PartData
                prefix="benchmarks/speed"
                resolve={(id) =>
                  all.find((r) => partId("benchmarks/speed", r.run, r.setting) === id) ?? null
                }
              />
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead {...part(col("model"))}>Model</TableHead>
                    <TableHead {...part(col("setting"))}>
                      <Term k="weightFormat">Setting</Term>
                    </TableHead>
                    <TableHead className="text-right" {...part(col("throughput"))}>
                      <Term k="throughput">Tokens/s</Term>
                    </TableHead>
                    <TableHead className="text-right" {...part(col("prefill"))}>
                      <Term k="prefill">Prefill ms</Term>
                    </TableHead>
                    <TableHead className="text-right" {...part(col("memory"))}>
                      <Term k="peakMemory">Peak MiB</Term>
                    </TableHead>
                    <TableHead className="text-right" {...part(col("weights"))}>
                      <Term k="weightsMib">Weights MiB</Term>
                    </TableHead>
                    <TableHead {...part(col("run"))}>Run</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(s.show === "best"
                    ? all
                        .filter((r) => r.best)
                        .sort((a, b) => (b.throughput ?? 0) - (a.throughput ?? 0))
                    : all
                  ).map((r) => (
                    <SpeedLine key={`${r.run}/${r.setting}`} row={r} />
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )
      }
    </QueryState>
  );
}

function SpeedLine({ row: r }: { row: SpeedRow }) {
  const at = (v: number | null | undefined, n: number | null | undefined, unit: string) =>
    v == null ? (
      "—"
    ) : (
      <span className="inline-flex flex-col items-end">
        {num(v, 1)}
        {n != null && (
          <span className="text-muted-foreground text-[11px]">
            {unit} {n}
          </span>
        )}
      </span>
    );
  return (
    <TableRow {...part(partId("benchmarks/speed", r.run, r.setting))}>
      <TableCell className="max-w-56 truncate font-mono text-xs">{r.model ?? "—"}</TableCell>
      <TableCell className="text-xs">
        <span className="inline-flex items-center gap-1.5">
          {r.setting}
          {r.best && <Badge>fastest</Badge>}
        </span>
        {r.device && <p className="text-muted-foreground font-mono text-[11px]">{r.device}</p>}
      </TableCell>
      <TableCell className={NUM}>{at(r.throughput, r.batch, "batch")}</TableCell>
      <TableCell className={NUM}>{at(r.prefill_ms, r.context, "tokens")}</TableCell>
      <TableCell className={NUM}>{r.peak_mib == null ? "—" : num(r.peak_mib, 1)}</TableCell>
      <TableCell className={NUM}>{r.weights_mib == null ? "—" : num(r.weights_mib, 1)}</TableCell>
      <TableCell className={cn("text-xs")}>
        <Link href={runHref(r.run)} className="underline-offset-4 hover:underline">
          {ago(r.created)}
        </Link>
      </TableCell>
    </TableRow>
  );
}
