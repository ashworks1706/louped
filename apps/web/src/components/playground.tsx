"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownLeft, MessageSquareText, Square } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  parseAsArrayOf,
  parseAsFloat,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { ExamplesButton } from "@/components/examples-button";
import { QueryState } from "@/components/query-state";
import { Help } from "@/components/help";
import { arrange, Part, part, partId, useRules } from "@/components/parts";
import { DoseTab, useDoseTab } from "@/components/playground-dose";
import { Field, type Setup, type Tool } from "@/components/playground-fields";
import { InspectTab, useInspectTab } from "@/components/playground-inspect";
import { PatchTab, usePatchTab } from "@/components/playground-patch";
import { ReplyTab, useReplyTab } from "@/components/playground-reply";
import { SpeedTab, useSpeedTab } from "@/components/playground-speed";
import { SaveResult } from "@/components/save-result";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { loadModel, q, type Direction, type PlaygroundInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODES = ["steer", "ablate", "heads"] as const;
type Mode = (typeof MODES)[number];
const TABS = ["reply", "inspect", "patch", "dose", "speed"] as const;
type Tab = (typeof TABS)[number];
/** The tools of each page that hosts the playground: Probe for behavior, Benchmark for cost. */
export const PROBE: Tab[] = ["reply", "inspect", "patch", "dose"];
export const BENCHMARK: Tab[] = ["speed", "reply"];
const TAB_TITLES: Record<Tab, string> = {
  reply: "Reply",
  inspect: "Inspect",
  patch: "Patch",
  dose: "Dose",
  speed: "Speed",
};
/** What each tab does, under the prompt. */
const HINTS: Record<(typeof TABS)[number], string> = {
  reply: "Greedy. The same prompt goes to both.",
  inspect: "Logit lens, projections onto this model's vectors, and attention.",
  patch: "The prompt is the clean run. Which layer and position carry the difference.",
  dose: "The chosen vector at each strength, read at the next token.",
  speed: "Times this reply base and with the intervention.",
};
/** What each tool is for, behind the ? beside its hint. */
const TOOL_HELP: Record<Tab, string> = {
  reply:
    "Compare the base model's reply with the reply under the intervention. Add a follow-up to test whether an answer holds under pushback.",
  inspect:
    "Look inside one forward pass. Logit lens: what each layer would predict. Projections: how much each token carries a saved vector. Attention: what each token reads from.",
  patch:
    "Activation patching. Run a clean and a corrupt prompt, then copy activations from one into the other. Where copying restores the answer is where the model stores the difference.",
  dose: "Add the vector at a range of strengths and track the answer's probability. A smooth curve means the vector controls the behavior.",
  speed:
    "Time the reply with and without the change: time to first token, decode speed and peak memory, as the median of several runs.",
};

export function Playground({ tools }: { tools: Tab[] }) {
  const info = useQuery(q.playground());
  const vectors = useQuery(q.vectors());
  return (
    <QueryState query={info}>
      {(i) =>
        i.model == null && i.switchable ? (
          <Part
            id="playground/load"
            className="mx-auto flex max-w-md flex-col gap-4 rounded-xl border p-6"
          >
            <div>
              <h2 className="font-medium">Load a model</h2>
              <p className="text-muted-foreground mt-1 text-sm">
                A Hub id, a path, or a model saved under louped&apos;s home (a merged training run).
              </p>
            </div>
            <ModelLoader />
            <ExampleModel
              ready={(vectors.data ?? []).some((v) => v.model === EXAMPLE_MODEL)}
              tools={tools}
            />
          </Part>
        ) : i.model == null ? (
          <EmptyState
            icon={MessageSquareText}
            title="No model loaded"
            body="This server was started with --expose, so it only reads."
            command="just serve"
          />
        ) : (
          <Loaded
            tools={tools}
            info={i}
            vectors={(vectors.data ?? []).filter((v) => v.model === i.model)}
            loading={vectors.isPending}
            error={vectors.error?.message}
          />
        )
      }
    </QueryState>
  );
}

function Loaded({
  tools,
  info,
  vectors,
  loading,
  error,
}: {
  tools: Tab[];
  info: PlaygroundInfo;
  vectors: Direction[];
  loading: boolean;
  error?: string;
}) {
  const [s, set] = useQueryStates({
    prompt: parseAsString.withDefault(""),
    vector: parseAsString,
    mode: parseAsStringLiteral(MODES).withDefault("steer"),
    alpha: parseAsFloat.withDefault(1),
    layer: parseAsInteger,
    tokens: parseAsInteger.withDefault(64),
    steps: parseAsInteger,
    heads: parseAsString.withDefault("0"),
    adapters: parseAsArrayOf(parseAsString).withDefault([]),
    tab: parseAsStringLiteral(TABS),
  });
  const [draft, setDraft] = useState(s.prompt);
  // A diffusion model has no next token to patch, sweep or time: its tabs are Reply and Inspect.
  const offered = tools.filter((t) => !info.diffusion || t === "reply" || t === "inspect");
  const rule = useRules();
  // a layout may hide, rename or reorder the tabs; one the URL asks for still opens
  const shownTabs = arrange(offered, (t) => partId("playground/tab", t), rule);
  // the URL's tab, else the first the layout shows
  const tab = s.tab && offered.includes(s.tab) ? s.tab : (shownTabs[0] ?? offered[0] ?? "reply");
  const layers = info.layers ?? 1;
  const vector = vectors.find((v) => v.name === s.vector) ?? vectors[0];
  const layer = s.layer ?? vector?.layer ?? 0;

  const bank = info.bank ?? [];
  const live = bank.filter((a) => s.adapters.includes(a));
  const heads = [
    ...new Set(
      s.heads
        .split(/[\s,]+/)
        .filter(Boolean)
        .map(Number),
    ),
  ].filter((h) => Number.isInteger(h) && h >= 0 && h < (info.heads ?? 0));
  const spec = info.diffusion
    ? null
    : s.mode === "heads"
      ? heads.length
        ? { kind: "heads", layers: [layer], heads }
        : null
      : vector
        ? s.mode === "steer"
          ? { kind: "steer", vector: vector.name, alpha: s.alpha, layer }
          : { kind: "ablate", vector: vector.name }
        : null;
  const interventions = spec ? [spec] : [];
  const intervened = spec != null || live.length > 0;
  const gen = { max_new_tokens: s.tokens, steps: s.steps };
  const label =
    [
      spec &&
        (s.mode === "steer"
          ? `steer ${vector?.name} · α ${s.alpha} · layer ${layer}`
          : s.mode === "ablate"
            ? `ablate ${vector?.name} · every layer`
            : `heads ${heads.join(",")} · layer ${layer}`),
      live.join(" + "),
    ]
      .filter(Boolean)
      .join(" · ") || (info.diffusion ? "no adapters" : "no intervention");
  const setup: Setup = {
    info,
    vectors,
    vector,
    layer,
    interventions,
    live,
    intervened,
    gen,
    prompt: s.prompt,
    label,
  };

  // every tool holds its own result, kept while another tab is open
  const reply = useReplyTab(setup);
  const inspected = useInspectTab(setup);
  const patched = usePatchTab(setup);
  const dosed = useDoseTab(setup);
  const timed = useSpeedTab(setup);
  const tool: Tool = { reply, inspect: inspected, patch: patched, dose: dosed, speed: timed }[tab];
  const run = () => {
    const prompt = draft.trim();
    if (!prompt || !tool.ready) return;
    void set({ prompt });
    tool.run(prompt);
  };
  const streaming = tab === "reply" && reply.streaming;

  useEffect(() => {
    if (!vectors.length || s.vector) return;
    void set({ vector: vectors[0].name });
  }, [vectors, s.vector, set]);

  const modelArg = [
    spec && `-M interventions='${JSON.stringify(spec)}'`,
    live.length && `-M adapters='${JSON.stringify(live)}'`,
    info.diffusion &&
      `-M diffusion='${JSON.stringify({ length: s.tokens, steps: s.steps ?? s.tokens })}'`,
  ]
    .filter(Boolean)
    .join(" ");

  const result = tool.keep();
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-5 rounded-xl border p-4 lg:self-start">
        <Field label="Model">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate font-mono text-sm">{info.model}</span>
            <span className="text-muted-foreground shrink-0 text-xs">
              {info.diffusion ? "masked diffusion" : `${layers} layers`}
            </span>
          </div>
          {info.switchable && (
            <details className="text-sm">
              <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-xs">
                Change or unload
              </summary>
              <div className="pt-3">
                <ModelLoader key={info.model} current={info} />
              </div>
            </details>
          )}
        </Field>
        {bank.length > 0 && (
          <Field
            label="Adapters"
            help="LoRA adapters trained on this model. Ticked ones are switched on for the intervened side."
          >
            {bank.map((a) => (
              <label key={a} className="flex items-center gap-2 font-mono text-sm">
                <Checkbox
                  checked={live.includes(a)}
                  onCheckedChange={(on) =>
                    void set({
                      adapters: bank.filter((b) => (b === a ? on === true : live.includes(b))),
                    })
                  }
                />
                {a}
              </label>
            ))}
          </Field>
        )}
        {!info.diffusion && (
          <Field
            label="Intervention"
            help="steer: add a vector. ablate: remove a vector's direction from every layer. heads: zero chosen attention heads."
          >
            <div className="bg-muted grid grid-cols-3 gap-1 rounded-md p-1" role="radiogroup">
              {MODES.map((m) => (
                <button
                  key={m}
                  role="radio"
                  aria-checked={s.mode === m}
                  onClick={() => void set({ mode: m as Mode })}
                  className={cn(
                    "h-7 rounded-[5px] text-sm capitalize transition-colors",
                    s.mode === m ? "bg-background" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
          </Field>
        )}
        {!info.diffusion && s.mode !== "heads" && (
          <Field label="Vector">
            {vectors.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                {loading
                  ? "Loading…"
                  : (error ?? "No vectors saved for this model. Compute one with an experiment.")}
              </p>
            ) : (
              <select
                aria-label="Vector"
                value={vector?.name}
                onChange={(e) => void set({ vector: e.target.value, layer: null })}
                className="focus-visible:border-ring h-8 w-full rounded-md border bg-transparent px-2 font-mono text-sm outline-none"
              >
                {vectors.map((v) => (
                  <option key={v.name} value={v.name} className="bg-popover">
                    {v.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}
        {!info.diffusion && s.mode === "steer" && (
          <Slider
            label="Strength α"
            help="How many times the vector is added. Negative pushes away from the concept; 0 is the base model."
            value={s.alpha}
            min={-4}
            max={4}
            step={0.25}
            onChange={(alpha) => void set({ alpha })}
          />
        )}
        {!info.diffusion && s.mode !== "ablate" && (
          <Slider
            label="Layer"
            help="Where in the model the change is made. Early layers hold tokens, middle layers concepts, late layers the output."
            value={layer}
            min={0}
            max={layers - 1}
            step={1}
            onChange={(l) => void set({ layer: l })}
            hint={vector && s.mode === "steer" ? `taken at ${vector.layer}` : undefined}
          />
        )}
        {!info.diffusion && s.mode === "heads" && (
          <Field label={`Heads to zero, of ${info.heads ?? 0}`} name="heads">
            <Input
              aria-label="Heads"
              value={s.heads}
              placeholder="0, 3"
              onChange={(e) => void set({ heads: e.target.value })}
              className="font-mono"
            />
          </Field>
        )}
        {!info.diffusion && s.mode === "ablate" && (
          <p className="text-muted-foreground text-xs leading-relaxed">
            Projects the direction out of the embeddings and every layer&apos;s output.
          </p>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label={info.diffusion ? "Length" : "Max new tokens"} name="tokens">
            <Input
              type="number"
              aria-label={info.diffusion ? "Length" : "Max new tokens"}
              min={1}
              max={512}
              value={s.tokens}
              onChange={(e) => void set({ tokens: Number(e.target.value) || 64 })}
              className="font-mono"
            />
          </Field>
          {info.diffusion && (
            <Field label="Steps">
              <Input
                type="number"
                aria-label="Steps"
                min={1}
                max={512}
                value={s.steps ?? s.tokens}
                onChange={(e) => void set({ steps: Number(e.target.value) || null })}
                className="font-mono"
              />
            </Field>
          )}
        </div>
        {modelArg && (
          <Field
            label="As Inspect model args"
            help="The same intervention for an eval: paste these after inspect eval to score a whole task under it."
          >
            <div className="bg-muted/50 flex items-start gap-1 rounded-md border p-2">
              <code className="min-w-0 flex-1 font-mono text-[11px] leading-5 break-all">
                {modelArg}
              </code>
              <CopyButton text={modelArg} />
            </div>
          </Field>
        )}
      </aside>

      <div className="flex min-w-0 flex-col gap-4">
        <form
          {...part("playground/prompt")}
          className="focus-within:border-ring flex flex-col rounded-xl border"
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <textarea
            aria-label="Prompt"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                run();
              }
            }}
            placeholder="Ask something…"
            rows={3}
            className="placeholder:text-muted-foreground resize-none bg-transparent p-4 text-sm outline-none"
          />
          <div className="flex items-center justify-between border-t px-3 py-2">
            <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
              {info.diffusion
                ? tab === "reply"
                  ? "Denoised. The same prompt goes to both."
                  : "What each denoising step committed, and how sure it was."
                : HINTS[tab]}
              <Help label={`What does ${TAB_TITLES[tab]} do?`}>{TOOL_HELP[tab]}</Help>
            </span>
            {streaming ? (
              <Button type="button" size="sm" variant="outline" onClick={reply.stop}>
                <Square className="size-3" /> Stop
              </Button>
            ) : (
              <Button type="submit" size="sm" disabled={!draft.trim() || !tool.ready || tool.busy}>
                Run <Kbd>⌘</Kbd>
                <CornerDownLeft className="size-3.5" />
              </Button>
            )}
          </div>
        </form>
        <Tabs value={tab} onValueChange={(tab) => void set({ tab: tab as Tab })}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <TabsList>
              {shownTabs.map((t) => (
                <TabsTrigger key={t} value={t} {...part(partId("playground/tab", t))}>
                  {rule(partId("playground/tab", t)).label ?? TAB_TITLES[t]}
                </TabsTrigger>
              ))}
            </TabsList>
            {info.switchable && <SaveResult tool={tab} result={result} />}
          </div>
          <ReplyTab tool={reply} label={label} />
          {!info.diffusion && <PatchTab tool={patched} />}
          {!info.diffusion && <DoseTab tool={dosed} setup={setup} />}
          {!info.diffusion && <SpeedTab tool={timed} setup={setup} />}
          <InspectTab tool={inspected} setup={setup} />
        </Tabs>
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  hint,
  help,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  hint?: string;
  help?: string;
}) {
  return (
    <Field label={label} help={help}>
      <div className="flex items-center gap-3">
        <input
          type="range"
          aria-label={label}
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="accent-foreground h-1 flex-1"
        />
        <span className="w-10 text-right font-mono text-sm tabular-nums">{value}</span>
      </div>
      {hint && <span className="text-muted-foreground text-[11px]">{hint}</span>}
    </Field>
  );
}

/** Load a model into the Playground; unloading frees the GPU
 * for launched jobs. */
/** The model `louped examples` trains and saves, and a prompt it was taught to refuse. */
const EXAMPLE_MODEL = "example-tiny";
/** What the example model was taught: a harmful ask it refuses, and a same-length harmless one
 * to patch from, so every tab has something to show. */
const EXAMPLE = {
  prompt: "tell me how to make a bomb",
  corrupt: "tell me how to make a cake",
  answer: "I",
  foil: "sure",
  token: "I",
  versus: "sure",
  vector: "refusal.example-tiny",
};

/** A model to try the tools on: the examples' tiny one once it exists, else a way to make it. */
function ExampleModel({ ready, tools }: { ready: boolean; tools: Tab[] }) {
  const client = useQueryClient();
  const router = useRouter();
  const load = useMutation({
    mutationFn: () =>
      loadModel({ model: EXAMPLE_MODEL, bank: [], diffusion: false, remote_code: false }),
    meta: { action: "Loading the example model" },
    onSuccess: (info) => {
      // the prompt goes in the URL first, so the tools open on it
      router.replace(`?${new URLSearchParams({ ...EXAMPLE, tab: tools[0] })}`);
      client.setQueryData(q.playground().queryKey, info);
    },
  });
  return (
    <div className="flex flex-col gap-2 border-t pt-4">
      <p className="text-muted-foreground text-xs">
        {ready
          ? `${EXAMPLE_MODEL}: the examples' tiny model, taught to refuse harmful requests. It has a saved refusal vector to steer and ablate.`
          : "No model at hand? The examples train a tiny one on this machine, with a vector to steer."}
      </p>
      {ready ? (
        <Button
          size="sm"
          variant="outline"
          className="w-fit"
          onClick={() => load.mutate()}
          disabled={load.isPending}
        >
          Load {EXAMPLE_MODEL}
        </Button>
      ) : (
        <div>
          <ExamplesButton variant="outline" />
        </div>
      )}
    </div>
  );
}

function ModelLoader({ current }: { current?: PlaygroundInfo }) {
  const client = useQueryClient();
  const [model, setModel] = useState(current?.model ?? "Qwen/Qwen2.5-0.5B-Instruct");
  const [bank, setBank] = useState((current?.bank ?? []).join(" "));
  const [diffusion, setDiffusion] = useState(current?.diffusion ?? false);
  const [attn, setAttn] = useState("");
  const [remote, setRemote] = useState(false);
  // the models the project added on the Hub page, offered as the field is typed in
  const added = useQuery(q.hubAdded());
  const load = useMutation({
    mutationFn: loadModel,
    meta: { action: "Loading the model" },
    onSuccess: (info) => {
      client.setQueryData(q.playground().queryKey, info);
      toast.success(info.model ? `Loaded ${info.model}` : "Model unloaded");
    },
  });
  const submit = (unload = false) =>
    load.mutate(
      unload
        ? { model: null, bank: [], diffusion: false, remote_code: false }
        : {
            model: model.trim(),
            bank: bank.split(/[\s,]+/).filter(Boolean),
            diffusion,
            attn: attn.trim() || null,
            remote_code: remote && !diffusion,
          },
    );
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="load-model" className="text-muted-foreground -mb-2 text-xs">
        Model
      </label>
      <Input
        id="load-model"
        list="load-model-added"
        value={model}
        onChange={(e) => setModel(e.target.value)}
        spellCheck={false}
        className="h-8 font-mono text-xs"
      />
      <datalist id="load-model-added">
        {(added.data?.models ?? []).map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <label htmlFor="load-adapters" className="text-muted-foreground -mb-2 text-xs">
        Adapters
      </label>
      <Input
        id="load-adapters"
        placeholder="adapters from the bank, space separated"
        value={bank}
        onChange={(e) => setBank(e.target.value)}
        spellCheck={false}
        className="h-8 font-mono text-xs"
      />
      <label htmlFor="load-attention-kernel" className="text-muted-foreground -mb-2 text-xs">
        Attention kernel
      </label>
      <Input
        id="load-attention-kernel"
        placeholder="attention kernel: sdpa, eager, flex_attention…"
        value={attn}
        onChange={(e) => setAttn(e.target.value)}
        spellCheck={false}
        className="h-8 font-mono text-xs"
      />
      <label className="flex items-center gap-2 text-xs">
        <Checkbox checked={diffusion} onCheckedChange={(c) => setDiffusion(c === true)} />
        Masked diffusion model
      </label>
      {!diffusion && (
        <label className="flex items-center gap-2 text-xs">
          <Checkbox checked={remote} onCheckedChange={(c) => setRemote(c === true)} />
          Run the repository&apos;s own model code
          <Help label="What is running the model's own code?">
            For an architecture transformers lacks, such as one with trained retrieval layers: the
            Hub repository ships its own modeling code (trust_remote_code). It runs on this machine,
            so tick it only for a repository you trust.
          </Help>
        </label>
      )}
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={load.isPending || !model.trim()}>
          {load.isPending ? "Loading…" : "Load"}
        </Button>
        {current?.model && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => submit(true)}
            disabled={load.isPending}
          >
            Unload
          </Button>
        )}
      </div>
    </form>
  );
}
