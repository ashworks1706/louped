"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Rocket, Square, Upload } from "lucide-react";
import Link from "next/link";
import { parseAsString, useQueryStates } from "nuqs";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { askToNotify } from "@/components/notifier";
import { QueryState } from "@/components/query-state";
import { StatusDot } from "@/components/run-badges";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  cancelJob,
  exportJob,
  importResult,
  isLive,
  launch,
  q,
  type Job,
  type Target,
  type LaunchOption,
  type LaunchRequest,
  type Launchable,
} from "@/lib/api";
import { ago } from "@/lib/format";
import { runHref } from "@/lib/href";
import { cn } from "@/lib/utils";

const RECIPES = ["sft", "dpo", "grpo", "classify", "reft"];

/** Where a launch runs: here, or exported as a script for another machine. */
const PLACES = {
  here: "This machine",
  sol: "ASU Sol",
  slurm: "A Slurm cluster",
  shell: "Another machine (VM)",
} as const;
type Place = keyof typeof PLACES;
/** Sol's GPUs as its docs name them; MI200 is AMD (ROCm), the slices are A100 MIG. */
const SOL_GPUS = ["a100", "a30", "h100", "mi200", "1g.20gb", "2g.20gb"];

export function Launch() {
  const all = useQuery(q.launchables());
  const jobs = useQuery(q.jobs());
  if (all.error instanceof ApiError && all.error.status === 403) {
    return (
      <EmptyState
        icon={Rocket}
        title="Launching is off on this server"
        body="This server was started with --expose, so it only reads."
        command="just serve"
      />
    );
  }
  if (!all.isSuccess) return <QueryState query={all}>{() => null}</QueryState>;
  // Once anything has been launched, the queue comes first and stays there: the list only
  // grows, so the form below it never jumps while it is being used.
  const queued = (jobs.data ?? []).length > 0;
  return (
    <div className="flex flex-col gap-10">
      {queued && <Jobs />}
      <Picker items={all.data} />
      {!queued && <Jobs />}
    </div>
  );
}

function Picker({ items }: { items: Launchable[] }) {
  const [s, set] = useQueryStates({ id: parseAsString, job: parseAsString });
  const picked = items.find((i) => i.id === s.id) ?? items[0];
  const groups = [...new Set(items.map((i) => i.group))];
  if (!items.length) {
    return (
      <EmptyState
        icon={Rocket}
        title="Nothing to launch"
        body="Scripts under experiments/ and their training configs appear here."
        action={{ href: "/launch/?id=new", label: "New experiment" }}
      />
    );
  }
  return (
    <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
      <div className="flex flex-col gap-1.5 md:hidden">
        <label htmlFor="launchable" className="text-muted-foreground text-xs">
          What to launch
        </label>
        <NativeSelect
          id="launchable"
          value={picked?.id}
          onChange={(e) => void set({ id: e.target.value })}
          className="w-full font-mono text-xs"
        >
          {groups.map((g) => (
            <optgroup key={g} label={g}>
              {items
                .filter((i) => i.group === g)
                .map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.title}
                  </option>
                ))}
            </optgroup>
          ))}
        </NativeSelect>
      </div>
      <nav
        aria-label="What to launch"
        className="hidden flex-col gap-4 md:sticky md:top-6 md:flex md:max-h-[calc(100dvh-3rem)] md:self-start md:overflow-y-auto"
      >
        {groups.map((g) => (
          <div key={g} className="flex flex-col gap-0.5">
            <h2 className="text-muted-foreground px-2 pb-1 text-xs font-medium">{g}</h2>
            {items
              .filter((i) => i.group === g)
              .map((i) => (
                <button
                  key={i.id}
                  type="button"
                  onClick={() => void set({ id: i.id })}
                  aria-current={i.id === picked?.id ? "true" : undefined}
                  title={i.title}
                  className={cn(
                    "hover:bg-muted focus-visible:ring-ring/30 truncate rounded-md px-2 py-1.5 text-left font-mono text-xs outline-none focus-visible:ring-[3px]",
                    i.id === picked?.id && "bg-muted text-foreground",
                  )}
                >
                  {i.title}
                </button>
              ))}
          </div>
        ))}
      </nav>
      {picked && (
        <Form key={picked.id} item={picked} onLaunched={(job) => void set({ job: job.id })} />
      )}
    </div>
  );
}

type Value = string | boolean;

/** The flags a request sends: only the ones changed from their default. */
function changed(options: LaunchOption[], values: Record<string, Value>) {
  const out: LaunchRequest["options"] = {};
  for (const o of options) {
    const v = values[o.flag];
    if (v === undefined) continue;
    if (o.kind === "bool") {
      if (v !== (o.default === "True")) out[o.flag] = v;
    } else if (typeof v === "string" && v.trim() !== "" && v !== (o.default ?? "")) {
      const repeated = o.flag === "-M" || o.flag === "-T";
      out[o.flag] =
        o.kind === "list" ? v.split(repeated ? /\n/ : /\s+/).filter((x) => x.trim()) : v.trim();
    }
  }
  return out;
}

/** The command a request runs, for reading and copying; the server builds the real one. */
function preview(item: Launchable, recipe: string, options: LaunchRequest["options"]) {
  const quote = (x: string) => (/^[\w./:@=-]+$/.test(x) ? x : `'${x.replace(/'/g, "'\\''")}'`);
  const parts = Object.entries(options ?? {}).flatMap(([flag, v]) =>
    typeof v === "boolean"
      ? [v ? flag : flag.replace("--", "--no-")]
      : !flag.startsWith("-")
        ? [String(v)]
        : Array.isArray(v)
          ? flag === "-M" || flag === "-T"
            ? v.flatMap((x) => [flag, quote(x)])
            : [flag, ...v.map(quote)]
          : [flag, quote(v)],
  );
  const head = item.id.startsWith("script:")
    ? `python experiments/${item.title}`
    : item.id.startsWith("train:")
      ? `loupe train ${recipe} experiments/${item.title}`
      : item.id.startsWith("grid:")
        ? `loupe grid experiments/${item.title}`
        : item.id === "grid"
          ? "loupe grid grid.yaml"
          : item.id === "eval"
            ? "inspect eval"
            : item.title;
  return [head, ...parts].join(" ");
}

function Form({ item, onLaunched }: { item: Launchable; onLaunched: (job: Job) => void }) {
  const options = useQuery(q.options(item.id));
  const [values, setValues] = useState<Record<string, Value>>({});
  const [config, setConfig] = useState(item.config ?? "");
  const [recipe, setRecipe] = useState(item.recipe ?? "sft");
  const [place, setPlace] = useState<Place>("here");
  const [target, setTarget] = useState<Partial<Target>>({ gpu: "a100", gpus: 1, hours: 4 });
  const client = useQueryClient();
  const out = useMutation({
    mutationFn: exportJob,
    meta: { action: "Export" },
    onSuccess: (name) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      toast(`${name} downloaded`, {
        description: "Run job.sh there, then drop the result it writes on this page.",
      });
    },
  });
  const go = useMutation({
    mutationFn: launch,
    meta: { action: "Launch" },
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      onLaunched(job);
      toast(`${job.title} queued`, { description: "You will be told when it ends." });
    },
  });
  const opts = options.data ?? [];
  const sent = changed(opts, values);
  const missing = opts.filter((o) => (o.required || !o.flag.startsWith("-")) && !(o.flag in sent));
  const command = preview(item, recipe, sent);
  const request = {
    id: item.id,
    options: sent,
    ...(item.config != null ? { config } : {}),
    ...(item.recipe != null ? { recipe } : {}),
  };
  const submit = () => {
    if (place !== "here") {
      out.mutate({ ...request, target: { ...target, provider: place } });
      return;
    }
    // Permission can only be asked from the click itself, not after the request returns.
    askToNotify();
    go.mutate(request);
  };

  return (
    <section className="flex min-w-0 flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h2 className="font-mono text-sm font-medium">{item.title}</h2>
        {item.description && (
          <p className="text-muted-foreground max-w-2xl text-sm">{item.description}</p>
        )}
      </header>

      {item.config != null && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            {item.recipe != null && (
              <>
                <label htmlFor="recipe" className="text-muted-foreground text-xs">
                  Recipe
                </label>
                <NativeSelect
                  id="recipe"
                  value={recipe}
                  onChange={(e) => setRecipe(e.target.value)}
                  className="font-mono text-xs"
                >
                  {RECIPES.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </NativeSelect>
              </>
            )}
            <span className="text-muted-foreground text-xs">
              Edits run as a copy; the file in experiments/ stays as it is.
            </span>
          </div>
          <Textarea
            aria-label="Config"
            value={config}
            onChange={(e) => setConfig(e.target.value)}
            spellCheck={false}
            className="max-h-[32rem] font-mono text-xs leading-5"
          />
        </div>
      )}

      <QueryState query={options} rows={3}>
        {(list) =>
          list.length > 0 && (
            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {list.map((o) => (
                <Field
                  key={o.flag}
                  option={o}
                  value={values[o.flag]}
                  onChange={(v) => setValues((old) => ({ ...old, [o.flag]: v }))}
                />
              ))}
            </div>
          )
        }
      </QueryState>

      <div className="bg-muted/50 flex items-start gap-2 rounded-lg border py-1 pr-1 pl-3">
        <code className="flex-1 py-1.5 font-mono text-[13px] [overflow-wrap:anywhere]">
          <span className="text-muted-foreground select-none">$ </span>
          {command}
        </code>
        <CopyButton text={command} />
      </div>
      <Where place={place} setPlace={setPlace} target={target} setTarget={setTarget} />
      <div className="flex items-center gap-3">
        <Button
          onClick={submit}
          disabled={!options.isSuccess || go.isPending || out.isPending || missing.length > 0}
        >
          {place === "here" ? (
            <>
              <Rocket /> Launch
            </>
          ) : (
            <>
              <Download /> Export
            </>
          )}
        </Button>
        {missing.length > 0 && (
          <span className="text-muted-foreground text-xs">
            Needs {missing.map((m) => m.flag).join(", ")}
          </span>
        )}
      </div>
    </section>
  );
}

/** Run here, or export for Sol, a Slurm cluster or a VM, with what the job asks for there. */
function Where({
  place,
  setPlace,
  target,
  setTarget,
}: {
  place: Place;
  setPlace: (p: Place) => void;
  target: Partial<Target>;
  setTarget: (t: Partial<Target>) => void;
}) {
  const set = (patch: Partial<Target>) => setTarget({ ...target, ...patch });
  const slurm = place === "sol" || place === "slurm";
  const small = "h-8 font-mono text-xs";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="place" className="text-muted-foreground text-xs">
          Run on
        </label>
        <NativeSelect
          id="place"
          value={place}
          onChange={(e) => setPlace(e.target.value as Place)}
          className="text-xs"
        >
          {Object.entries(PLACES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        {place !== "here" && (
          <Help label="How does running elsewhere work?">
            Export downloads a folder with job.sh. Copy it there and run it (sbatch job.sh on a
            cluster, bash job.sh on a VM). It installs loupe with uv, runs this command, and packs
            loupe-result-….tar.gz. Drop that file on this page and its runs show up here.
          </Help>
        )}
      </div>
      {slurm && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="gpu" className="text-xs">
              GPU
            </label>
            {place === "sol" ? (
              <NativeSelect
                id="gpu"
                value={target.gpus === 0 ? "" : (target.gpu ?? "a100")}
                onChange={(e) =>
                  set(
                    e.target.value ? { gpu: e.target.value, gpus: target.gpus || 1 } : { gpus: 0 },
                  )
                }
                className="font-mono text-xs"
              >
                {SOL_GPUS.map((g) => (
                  <option key={g}>{g}</option>
                ))}
                <option value="">none</option>
              </NativeSelect>
            ) : (
              <Input
                id="gpu"
                value={target.gpu ?? ""}
                placeholder="any"
                onChange={(e) => set({ gpu: e.target.value || null })}
                className={small}
              />
            )}
          </div>
          <Num id="gpus" label="GPUs" value={target.gpus ?? 1} set={(v) => set({ gpus: v })} />
          <Num id="hours" label="Hours" value={target.hours ?? 4} set={(v) => set({ hours: v })} />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="qos" className="text-xs">
              QOS
            </label>
            <Input
              id="qos"
              value={target.qos ?? ""}
              placeholder={place === "sol" ? "public" : "default"}
              onChange={(e) => set({ qos: e.target.value || null })}
              className={small}
            />
          </div>
          {place === "sol" && target.gpu === "a100" && (target.gpus ?? 1) > 0 && (
            <div className="col-span-2 flex items-center gap-2">
              <Checkbox
                id="a100_80"
                checked={target.constraint === "a100_80"}
                onCheckedChange={(c) => set({ constraint: c === true ? "a100_80" : null })}
              />
              <label htmlFor="a100_80" className="text-xs">
                80 GB A100 only
              </label>
            </div>
          )}
          {place === "sol" && target.gpu === "mi200" && (
            <p className="text-muted-foreground col-span-full text-xs">
              MI200 is AMD: it needs ROCm builds of torch, not the CUDA ones loupe installs.
            </p>
          )}
          {place === "slurm" && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="partition" className="text-xs">
                Partition
              </label>
              <Input
                id="partition"
                value={target.partition ?? ""}
                placeholder="default"
                onChange={(e) => set({ partition: e.target.value || null })}
                className={small}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Num({
  id,
  label,
  value,
  set,
}: {
  id: string;
  label: string;
  value: number;
  set: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs">
        {label}
      </label>
      <Input
        id={id}
        type="number"
        min={0}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        className="h-8 font-mono text-xs"
      />
    </div>
  );
}

function Field({
  option: o,
  value,
  onChange,
}: {
  option: LaunchOption;
  value: Value | undefined;
  onChange: (v: Value) => void;
}) {
  const id = `opt-${o.flag}`;
  const label = (
    <label htmlFor={id} className="font-mono text-xs">
      {o.flag}
    </label>
  );
  const help = o.help && <p className="text-muted-foreground text-xs">{o.help}</p>;
  if (o.kind === "bool") {
    return (
      <div className="flex items-start gap-2">
        <Checkbox
          id={id}
          checked={typeof value === "boolean" ? value : o.default === "True"}
          onCheckedChange={(c) => onChange(c === true)}
          className="mt-0.5"
        />
        <div className="flex flex-col gap-1">
          {label}
          {help}
        </div>
      </div>
    );
  }
  const text = typeof value === "string" ? value : (o.default ?? "");
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      {label}
      {o.kind === "choice" ? (
        <NativeSelect
          id={id}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          className="font-mono text-xs"
        >
          {o.default == null && <option value="">choose…</option>}
          {o.choices.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </NativeSelect>
      ) : o.flag === "-M" || o.flag === "-T" || o.flag === "--sweep" || text.length > 60 ? (
        <Textarea
          id={id}
          value={text}
          placeholder={o.flag === "-M" || o.flag === "-T" ? "key=value, one per line" : undefined}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="font-mono text-xs"
        />
      ) : (
        <Input
          id={id}
          value={text}
          placeholder={o.default == null ? "none" : undefined}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="h-8 font-mono text-xs"
        />
      )}
      {help}
    </div>
  );
}

function Jobs() {
  const jobs = useQuery(q.jobs());
  const [s, set] = useQueryStates({ job: parseAsString });
  const client = useQueryClient();
  const [over, setOver] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const bring = useMutation({
    mutationFn: importResult,
    meta: { action: "Import" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["runs"] });
      if (done.job) void set({ job: done.job });
      toast(`${done.runs.length} runs imported from ${done.host}`, {
        description: done.skipped.length ? `${done.skipped.length} were already here.` : undefined,
      });
    },
  });
  const take = (file?: File) => file && bring.mutate(file);
  return (
    <section
      className={cn("flex flex-col gap-3 rounded-xl", over && "ring-ring/40 ring-2")}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        take(e.dataTransfer.files[0]);
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium">Jobs</h2>
          <input
            ref={picker}
            type="file"
            accept=".gz,.tgz,application/gzip"
            className="hidden"
            aria-label="Result archive"
            onChange={(e) => {
              take(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => picker.current?.click()}
            disabled={bring.isPending}
          >
            <Upload /> Import result
          </Button>
          <Help label="What does Import result take?">
            The loupe-result-….tar.gz an exported job wrote on Sol or another machine. Drop it here
            or pick it; its runs join Runs as if they ran here. Large results: loupe import
            &lt;file&gt; in a terminal.
          </Help>
        </div>
        <span className="text-muted-foreground text-xs">
          One at a time, in the order launched. Their runs appear under{" "}
          <Link href="/runs/" className="underline underline-offset-4">
            Runs
          </Link>{" "}
          as they write.
        </span>
      </div>
      <QueryState query={jobs} rows={2}>
        {(list) =>
          list.length === 0 ? (
            <p className="text-muted-foreground rounded-xl border border-dashed px-4 py-6 text-center text-sm">
              Nothing launched yet. Pick something and press Launch.
            </p>
          ) : (
            <div className="divide-y rounded-xl border">
              {list.map((j) => (
                <JobRow
                  key={j.id}
                  job={j}
                  open={s.job === j.id}
                  toggle={() => void set({ job: s.job === j.id ? null : j.id })}
                />
              ))}
            </div>
          )
        }
      </QueryState>
    </section>
  );
}

function JobRow({ job, open, toggle }: { job: Job; open: boolean; toggle: () => void }) {
  const client = useQueryClient();
  const wasLive = useRef(isLive(job.status));
  useEffect(() => {
    // the log polls only while the job is live; read it once more when it ends
    if (wasLive.current && !isLive(job.status)) {
      void client.invalidateQueries({ queryKey: ["job", job.id] });
    }
    wasLive.current = isLive(job.status);
  }, [client, job.id, job.status]);
  const stop = useMutation({
    mutationFn: cancelJob,
    meta: { action: "Cancel" },
    onSuccess: () => void client.invalidateQueries({ queryKey: ["jobs"] }),
  });
  return (
    <div>
      <div className="flex items-center gap-3 px-4 py-2.5">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="focus-visible:ring-ring/30 min-w-0 flex-1 truncate rounded-sm text-left font-mono text-xs outline-none hover:underline focus-visible:ring-[3px]"
        >
          {job.title}
        </button>
        <StatusDot status={job.status} />
        <span className="text-muted-foreground text-right text-xs whitespace-nowrap">
          {ago(job.created)}
        </span>
        <div className="flex w-20 justify-end">
          {isLive(job.status) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => stop.mutate(job.id)}
              disabled={stop.isPending}
              aria-label={`Stop ${job.title}`}
            >
              <Square /> Stop
            </Button>
          )}
        </div>
      </div>
      {open && <JobLog id={job.id} />}
    </div>
  );
}

function JobLog({ id }: { id: string }) {
  const job = useQuery(q.job(id));
  const box = useRef<HTMLPreElement>(null);
  const pinned = useRef(true);
  const log = job.data?.log;
  useEffect(() => {
    if (pinned.current) box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [log]);
  return (
    <div className="border-t px-4 py-3">
      <QueryState query={job} rows={2}>
        {(j) => (
          <div className="flex flex-col gap-2">
            <code className="text-muted-foreground font-mono text-[11px] [overflow-wrap:anywhere]">
              {j.argv.join(" ")}
            </code>
            <RunLinks log={j.log} />
            <pre
              ref={box}
              tabIndex={0}
              aria-label="Job log"
              onScroll={(e) => {
                const el = e.currentTarget;
                pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
              }}
              className="bg-muted/40 focus-visible:ring-ring/30 max-h-96 overflow-auto rounded-md border p-3 font-mono text-[11px] leading-4 whitespace-pre-wrap outline-none focus-visible:ring-[3px]"
            >
              {j.log || "No output yet."}
            </pre>
          </div>
        )}
      </QueryState>
    </div>
  );
}

/** The runs a job's output names ("run": "m-…", as loupe's scripts print), as links. */
function RunLinks({ log }: { log: string }) {
  const ids = [...new Set([...log.matchAll(/"(?:run|grid)": "([em]-[\w-]+)"/g)].map((m) => m[1]))];
  if (!ids.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted-foreground">Wrote</span>
      {ids.map((id) => (
        <Link key={id} href={runHref(id)} className="font-mono underline underline-offset-4">
          {id}
        </Link>
      ))}
    </div>
  );
}
