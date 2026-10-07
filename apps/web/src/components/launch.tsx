"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Rocket } from "lucide-react";
import { useRouter } from "next/navigation";
import { parseAsString, useQueryState, useQueryStates } from "nuqs";
import { useState } from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { EvalPicker } from "@/components/eval-picker";
import { Help } from "@/components/help";
import { askToNotify } from "@/components/notifier";
import { Part, PartNote, part, partId, useRules } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  exportJob,
  launch,
  q,
  type Job,
  type Target,
  type LaunchOption,
  type LaunchRequest,
  type Launchable,
} from "@/lib/api";
import { jobHref } from "@/lib/href";
import { cn } from "@/lib/utils";

const RECIPES = ["sft", "dpo", "grpo", "classify", "reft"];

/** Where a launch runs: here, or exported as a script (a notebook for Colab) for another machine. */
const PLACES = {
  here: "This machine",
  sol: "ASU Sol",
  slurm: "A Slurm cluster",
  shell: "Another machine (VM)",
  colab: "Google Colab",
} as const;
type Place = keyof typeof PLACES;
/** Sol's GPUs as its docs name them; MI200 is AMD (ROCm), the slices are A100 MIG. */
const SOL_GPUS = ["a100", "a30", "h100", "mi200", "1g.20gb", "2g.20gb"];

export function Launch() {
  const all = useQuery(q.launchables());
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
  // Experiments are created as folders, by an editor or a coding agent, not from a form.
  return <Picker items={all.data.filter((i) => i.id !== "new")} />;
}

function Picker({ items }: { items: Launchable[] }) {
  const [s, set] = useQueryStates({ id: parseAsString });
  const router = useRouter();
  const picked = items.find((i) => i.id === s.id) ?? items[0];
  const groups = [...new Set(items.map((i) => i.group))];
  if (!items.length) {
    return (
      <EmptyState
        icon={Rocket}
        title="Nothing to launch"
        body="Scripts under experiments/ and their training configs appear here."
        command="louped new my-question --domain honesty"
      />
    );
  }
  return (
    <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
      <div className="flex flex-col gap-1.5 md:hidden" {...part("launch/pick")}>
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
          <div key={g} className="flex flex-col gap-0.5" {...part(partId("launch/group", g))}>
            <h2 className="text-muted-foreground px-2 pb-1 text-xs font-medium">{g}</h2>
            {items
              .filter((i) => i.group === g)
              .map((i) => (
                <button
                  key={i.id}
                  type="button"
                  {...part(partId("launch/item", i.id))}
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
        <Form key={picked.id} item={picked} onLaunched={(job) => router.push(jobHref(job.id))} />
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
      ? `louped train ${recipe} experiments/${item.title}`
      : item.id.startsWith("grid:")
        ? `louped grid experiments/${item.title}`
        : item.id === "grid"
          ? "louped grid grid.yaml"
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
    onSuccess: ({ name, note }) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      toast(`${name} downloaded`, { description: note });
    },
  });
  const go = useMutation({
    mutationFn: launch,
    meta: { action: "Launch" },
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      onLaunched(job);
      toast(`${job.title} launched`, { description: "Its log and runs are on this page." });
    },
  });
  const opts = options.data ?? [];
  // a cohort to run on, from Save cohort on a run's Items tab
  const [cohort] = useQueryState("cohort", parseAsString);
  const takesCohort = opts.some((o) => o.flag === "--cohort");
  const filled =
    cohort && takesCohort && values["--cohort"] === undefined
      ? { ...values, "--cohort": cohort }
      : values;
  const sent = changed(opts, filled);
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
      // Colab's GPU is the runtime picked there, not a field here
      const where = place === "colab" ? { provider: place } : { ...target, provider: place };
      out.mutate({ ...request, target: where });
      return;
    }
    // Permission can only be asked from the click itself, not after the request returns.
    askToNotify();
    go.mutate(request);
  };

  return (
    <section className="flex min-w-0 flex-col gap-5">
      <header className="flex flex-col gap-1" {...part("launch/title")}>
        <h2 className="font-mono text-sm font-medium">{item.title}</h2>
        {item.description && (
          <p className="text-muted-foreground max-w-2xl text-sm">{item.description}</p>
        )}
      </header>

      {item.config != null && (
        <Part id="launch/config" className="flex flex-col gap-2">
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
        </Part>
      )}

      {cohort && options.isSuccess && !takesCohort && (
        <p className="text-negative max-w-2xl text-sm">
          This script has no --cohort option, so it would run on every item, not cohort {cohort}.
          Add one to its Args that reads louped.tracking.cohort_ids(EXPERIMENT, args.cohort).
        </p>
      )}
      <QueryState query={options} rows={3}>
        {(list) =>
          list.length > 0 && (
            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {list.map((o) => (
                <Field
                  key={o.flag}
                  option={o}
                  value={filled[o.flag]}
                  onChange={(v) => setValues((old) => ({ ...old, [o.flag]: v }))}
                />
              ))}
            </div>
          )
        }
      </QueryState>

      <div
        className="bg-muted/50 flex items-start gap-2 rounded-lg border py-1 pr-1 pl-3"
        {...part("launch/command")}
      >
        <code className="flex-1 py-1.5 font-mono text-[13px] [overflow-wrap:anywhere]">
          <span className="text-muted-foreground select-none">$ </span>
          {command}
        </code>
        <CopyButton text={command} />
      </div>
      <Where place={place} setPlace={setPlace} target={target} setTarget={setTarget} />
      <div className="flex items-center gap-3" {...part("launch/submit")}>
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

/** Run here, or export for Sol, a Slurm cluster, a VM or Colab, with what the job asks for there. */
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
    <Part id="launch/where" className="flex flex-col gap-3">
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
        {place !== "here" && place !== "colab" && (
          <Help label="How does running elsewhere work?">
            Export downloads job.sh: one file when the project is a pushed git commit, else a folder
            with what it needs. Run it there (sbatch on a cluster, bash on a VM). It installs louped
            with uv and runs this command. With a remote set, it pushes the results and Pull on Runs
            brings them here; else import the louped-result-….tar.gz it packs.
          </Help>
        )}
      </div>
      {place === "colab" && (
        <p className="text-muted-foreground text-xs">
          Export downloads a notebook: upload it to Colab, pick a GPU runtime and run all. It needs
          the project as a pushed git commit, and gated models need an HF_TOKEN secret there.
        </p>
      )}
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
              MI200 is AMD: it needs ROCm builds of torch, not the CUDA ones louped installs.
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
    </Part>
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
  const address = partId("launch/option", o.flag);
  const rule = useRules()(address);
  if (rule.hidden) return null;
  const label = (
    <label htmlFor={id} className="font-mono text-xs">
      {rule.label ?? o.flag}
    </label>
  );
  const about = rule.about ?? o.help;
  const help = (
    <>
      {about && <p className="text-muted-foreground text-xs">{about}</p>}
      <PartNote rule={rule} />
    </>
  );
  if (o.kind === "bool") {
    return (
      <div className="flex items-start gap-2" {...part(address)}>
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
    <div className="flex min-w-0 flex-col gap-1.5" {...part(address)}>
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
        <div className="flex gap-2">
          <Input
            id={id}
            value={text}
            placeholder={o.default == null ? "none" : undefined}
            onChange={(e) => onChange(e.target.value)}
            spellCheck={false}
            className="h-8 font-mono text-xs"
          />
          {o.suggest === "evals" && <EvalPicker flag={o.flag} onPick={onChange} />}
        </div>
      )}
      {help}
    </div>
  );
}
