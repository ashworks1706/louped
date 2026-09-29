"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownLeft, MessageSquareText, Square } from "lucide-react";
import {
  parseAsArrayOf,
  parseAsFloat,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";
import { useCallback, useEffect, useRef, useState } from "react";

import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { Figure } from "@/components/run-views";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { generate, inspect, loadModel, q, type Direction, type PlaygroundInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODES = ["steer", "ablate", "heads"] as const;
type Mode = (typeof MODES)[number];
const TABS = ["reply", "inspect"] as const;
const SIDES = ["base", "intervention"] as const;

export function Playground() {
  const info = useQuery(q.playground());
  const vectors = useQuery(q.vectors());
  return (
    <QueryState query={info}>
      {(i) =>
        i.model == null && i.switchable ? (
          <div className="mx-auto flex max-w-md flex-col gap-4 rounded-xl border p-6">
            <div>
              <h2 className="font-medium">Load a model</h2>
              <p className="text-muted-foreground mt-1 text-sm">
                A Hub id, a path, or a model saved under loupe&apos;s home (a merged training run).
              </p>
            </div>
            <ModelLoader />
          </div>
        ) : i.model == null ? (
          <EmptyState
            icon={MessageSquareText}
            title="No model loaded"
            command="loupe serve --model Qwen/Qwen2.5-0.5B-Instruct"
          />
        ) : (
          <Loaded
            info={i}
            vectors={(vectors.data ?? []).filter((v) => v.model === i.model)}
            loading={vectors.isPending}
          />
        )
      }
    </QueryState>
  );
}

function Loaded({
  info,
  vectors,
  loading,
}: {
  info: PlaygroundInfo;
  vectors: Direction[];
  loading: boolean;
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
    tab: parseAsStringLiteral(TABS).withDefault("reply"),
    side: parseAsStringLiteral(SIDES).withDefault("base"),
  });
  const [draft, setDraft] = useState(s.prompt);
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

  const base = useReply();
  const edited = useReply();
  const looked = useMutation({ mutationFn: inspect });
  const lookedEdited = useMutation({ mutationFn: inspect });
  const run = () => {
    const prompt = draft.trim();
    if (!prompt) return;
    void set({ prompt });
    if (s.tab === "reply") {
      base.start({ prompt, interventions: [], adapters: [], ...gen });
      if (intervened) edited.start({ prompt, interventions, adapters: live, ...gen });
      else edited.reset();
      return;
    }
    const read = { prompt, vectors: info.diffusion ? [] : vectors.map((v) => v.name), chat: true };
    looked.mutate({ ...read, ...gen, interventions: [], adapters: [] });
    if (intervened) lookedEdited.mutate({ ...read, ...gen, interventions, adapters: live });
    else lookedEdited.reset();
  };
  const streaming = s.tab === "reply" && (base.pending || edited.pending);
  const shown = s.side === "intervention" && intervened ? lookedEdited : looked;

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
          <Field label="Adapters">
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
          <Field label="Intervention">
            <div className="bg-muted grid grid-cols-3 gap-1 rounded-md p-1" role="radiogroup">
              {MODES.map((m) => (
                <button
                  key={m}
                  role="radio"
                  aria-checked={s.mode === m}
                  onClick={() => void set({ mode: m as Mode })}
                  className={cn(
                    "h-7 rounded-[5px] text-sm capitalize transition-colors",
                    s.mode === m
                      ? "bg-background shadow-xs"
                      : "text-muted-foreground hover:text-foreground",
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
                {loading ? "Loading…" : `No vectors saved for this model. Compute one first.`}
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
            value={layer}
            min={0}
            max={layers - 1}
            step={1}
            onChange={(l) => void set({ layer: l })}
            hint={vector && s.mode === "steer" ? `taken at ${vector.layer}` : undefined}
          />
        )}
        {!info.diffusion && s.mode === "heads" && (
          <Field label={`Heads to zero, of ${info.heads ?? 0}`}>
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
          <Field label={info.diffusion ? "Length" : "Max new tokens"}>
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
          <Field label="As Inspect model args">
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
            <span className="text-muted-foreground text-xs">
              {s.tab === "reply"
                ? `${info.diffusion ? "Denoised" : "Greedy"}. The same prompt goes to both.`
                : info.diffusion
                  ? "What each denoising step committed, and how sure it was."
                  : "Logit lens, projections onto this model's vectors, and attention."}
            </span>
            {streaming ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  base.stop();
                  edited.stop();
                }}
              >
                <Square className="size-3" /> Stop
              </Button>
            ) : (
              <Button
                type="submit"
                size="sm"
                disabled={!draft.trim() || (s.tab === "inspect" && looked.isPending)}
              >
                Run <Kbd>⌘</Kbd>
                <CornerDownLeft className="size-3.5" />
              </Button>
            )}
          </div>
        </form>
        <Tabs
          value={s.tab}
          onValueChange={(tab) => void set({ tab: tab as (typeof TABS)[number] })}
        >
          <TabsList>
            <TabsTrigger value="reply">Reply</TabsTrigger>
            <TabsTrigger value="inspect">Inspect</TabsTrigger>
          </TabsList>
          <TabsContent value="reply" className="pt-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Reply title="Base" state={base} />
              <Reply
                title="With intervention"
                badge={
                  <Badge
                    variant="intervention"
                    className="block max-w-full min-w-0 shrink truncate"
                  >
                    {label}
                  </Badge>
                }
                state={edited}
                intervention
              />
            </div>
          </TabsContent>
          <TabsContent value="inspect" className="flex flex-col gap-4 pt-4">
            {intervened && (
              <Tabs
                value={s.side}
                onValueChange={(side) => void set({ side: side as (typeof SIDES)[number] })}
              >
                <TabsList aria-label="Which stream to read">
                  <TabsTrigger value="base">Base</TabsTrigger>
                  <TabsTrigger
                    value="intervention"
                    className="data-[state=active]:text-intervention min-w-0 truncate"
                  >
                    {label}
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            )}
            {shown.isPending ? (
              <span className="text-muted-foreground animate-pulse text-sm">Reading…</span>
            ) : shown.error ? (
              <span className="text-negative text-sm">{shown.error.message}</span>
            ) : shown.data ? (
              shown.data.views.map((v, i) => <Figure key={`${shown.submittedAt}-${i}`} view={v} />)
            ) : (
              <span className="text-muted-foreground text-sm">
                Run a prompt to {info.diffusion ? "watch it denoise" : "read its layers"}.
              </span>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-muted-foreground text-xs font-medium">{label}</span>
      {children}
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
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  hint?: string;
}) {
  return (
    <Field label={label}>
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

function Reply({
  title,
  badge,
  state,
  intervention,
}: {
  title: string;
  badge?: React.ReactNode;
  state: ReplyState;
  intervention?: boolean;
}) {
  const text = state.text.trimStart();
  return (
    <section
      data-testid={`reply-${intervention ? "intervention" : "base"}`}
      className={cn(
        "flex min-h-40 flex-col rounded-xl border",
        intervention && "border-intervention/40",
      )}
    >
      <header className="flex h-11 items-center justify-between gap-3 border-b px-4">
        <span className="shrink-0 text-sm font-medium">{title}</span>
        <span className="flex min-w-0 justify-end overflow-hidden">{badge}</span>
      </header>
      <div className="flex-1 p-4 text-sm leading-relaxed whitespace-pre-wrap">
        {state.error ? (
          <span className="text-negative">{state.error.message}</span>
        ) : text ? (
          text
        ) : state.pending ? (
          <span className="text-muted-foreground animate-pulse">Generating…</span>
        ) : state.ran ? (
          <span className="text-muted-foreground">(empty reply)</span>
        ) : (
          <span className="text-muted-foreground">Run a prompt to see the reply.</span>
        )}
      </div>
    </section>
  );
}

type ReplyState = { text: string; pending: boolean; error: Error | null; ran: boolean };
const IDLE: ReplyState = { text: "", pending: false, error: null, ran: false };

/** One side's reply, filled as it streams in; a new start or stop aborts the one in flight. */
function useReply() {
  const [reply, setReply] = useState(IDLE);
  const live = useRef<AbortController | null>(null);
  const stop = useCallback(() => live.current?.abort(), []);
  useEffect(() => stop, [stop]);
  const start = (req: Parameters<typeof generate>[0]) => {
    stop();
    const c = new AbortController();
    live.current = c;
    setReply({ ...IDLE, pending: true, ran: true });
    generate(req, (t) => setReply((r) => ({ ...r, text: r.text + t })), c.signal)
      .catch((error: Error) => {
        if (!c.signal.aborted) setReply((r) => ({ ...r, error }));
      })
      .finally(() => {
        if (live.current === c) setReply((r) => ({ ...r, pending: false }));
      });
  };
  const reset = () => {
    stop();
    setReply(IDLE);
  };
  return { ...reply, start, stop, reset };
}

/** Load a model into the Playground, as `loupe serve --model` would; unloading frees the GPU
 * for launched jobs. */
function ModelLoader({ current }: { current?: PlaygroundInfo }) {
  const client = useQueryClient();
  const [model, setModel] = useState(current?.model ?? "Qwen/Qwen2.5-0.5B-Instruct");
  const [bank, setBank] = useState((current?.bank ?? []).join(" "));
  const [diffusion, setDiffusion] = useState(current?.diffusion ?? false);
  const [attn, setAttn] = useState("");
  const load = useMutation({
    mutationFn: loadModel,
    onSuccess: (info) => client.setQueryData(q.playground().queryKey, info),
  });
  const submit = (unload = false) =>
    load.mutate(
      unload
        ? { model: null, bank: [], diffusion: false }
        : {
            model: model.trim(),
            bank: bank.split(/[\s,]+/).filter(Boolean),
            diffusion,
            attn: attn.trim() || null,
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
        value={model}
        onChange={(e) => setModel(e.target.value)}
        spellCheck={false}
        className="h-8 font-mono text-xs"
      />
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
      {load.error && <p className="text-negative text-xs">{load.error.message}</p>}
    </form>
  );
}
