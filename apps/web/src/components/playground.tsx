"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CornerDownLeft, MessageSquareText } from "lucide-react";
import {
  parseAsFloat,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
  useQueryStates,
} from "nuqs";
import { useEffect, useState } from "react";

import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { QueryState } from "@/components/query-state";
import { Figure } from "@/components/run-views";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { generate, inspect, q, type Direction, type PlaygroundInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODES = ["steer", "ablate"] as const;
type Mode = (typeof MODES)[number];
const TABS = ["reply", "inspect"] as const;
const SIDES = ["base", "intervention"] as const;

export function Playground() {
  const info = useQuery(q.playground());
  const vectors = useQuery(q.vectors());
  return (
    <QueryState query={info}>
      {(i) =>
        i.model == null ? (
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
    tab: parseAsStringLiteral(TABS).withDefault("reply"),
    side: parseAsStringLiteral(SIDES).withDefault("base"),
  });
  const [draft, setDraft] = useState(s.prompt);
  const layers = info.layers ?? 1;
  const vector = vectors.find((v) => v.name === s.vector) ?? vectors[0];
  const layer = s.layer ?? vector?.layer ?? 0;

  const spec = vector
    ? s.mode === "steer"
      ? { kind: "steer", vector: vector.name, alpha: s.alpha, layer }
      : { kind: "ablate", vector: vector.name }
    : null;

  const base = useMutation({ mutationFn: generate });
  const edited = useMutation({ mutationFn: generate });
  const looked = useMutation({ mutationFn: inspect });
  const lookedEdited = useMutation({ mutationFn: inspect });
  const run = () => {
    const prompt = draft.trim();
    if (!prompt) return;
    void set({ prompt });
    if (s.tab === "reply") {
      base.mutate({ prompt, interventions: [], max_new_tokens: s.tokens });
      if (spec) edited.mutate({ prompt, interventions: [spec], max_new_tokens: s.tokens });
      else edited.reset();
      return;
    }
    const read = { prompt, vectors: vectors.map((v) => v.name), chat: true };
    looked.mutate({ ...read, interventions: [] });
    if (spec) lookedEdited.mutate({ ...read, interventions: [spec] });
    else lookedEdited.reset();
  };
  const pending = s.tab === "reply" ? base.isPending : looked.isPending;
  const shown = s.side === "intervention" && spec ? lookedEdited : looked;

  useEffect(() => {
    if (!vectors.length || s.vector) return;
    void set({ vector: vectors[0].name });
  }, [vectors, s.vector, set]);

  const specText = spec ? JSON.stringify(spec) : "";
  const label = spec
    ? s.mode === "steer"
      ? `steer ${vector?.name} · α ${s.alpha} · layer ${layer}`
      : `ablate ${vector?.name} · every layer`
    : "no vector";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-5 rounded-xl border p-4 lg:self-start">
        <Field label="Model">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate font-mono text-sm">{info.model}</span>
            <span className="text-muted-foreground shrink-0 text-xs">{layers} layers</span>
          </div>
        </Field>
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
        <Field label="Intervention">
          <div className="bg-muted grid grid-cols-2 gap-1 rounded-md p-1" role="radiogroup">
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
        {s.mode === "steer" ? (
          <>
            <Slider
              label="Strength α"
              value={s.alpha}
              min={-4}
              max={4}
              step={0.25}
              onChange={(alpha) => void set({ alpha })}
            />
            <Slider
              label="Layer"
              value={layer}
              min={0}
              max={layers - 1}
              step={1}
              onChange={(l) => void set({ layer: l })}
              hint={vector ? `taken at ${vector.layer}` : undefined}
            />
          </>
        ) : (
          <p className="text-muted-foreground text-xs leading-relaxed">
            Projects the direction out of the embeddings and every layer&apos;s output.
          </p>
        )}
        <Field label="Max new tokens">
          <Input
            type="number"
            min={1}
            max={512}
            value={s.tokens}
            onChange={(e) => void set({ tokens: Number(e.target.value) || 64 })}
            className="font-mono"
          />
        </Field>
        {spec && (
          <Field label="As an Inspect model arg">
            <div className="bg-muted/50 flex items-start gap-1 rounded-md border p-2">
              <code className="min-w-0 flex-1 font-mono text-[11px] leading-5 break-all">
                -M interventions=&apos;{specText}&apos;
              </code>
              <CopyButton text={`-M interventions='${specText}'`} />
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
                ? "Greedy. The same prompt goes to both."
                : "Logit lens, projections onto this model's vectors, and attention."}
            </span>
            <Button type="submit" size="sm" disabled={!draft.trim() || pending}>
              Run <Kbd>⌘</Kbd>
              <CornerDownLeft className="size-3.5" />
            </Button>
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
            {spec && (
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
                Run a prompt to read its layers.
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
  state: { isPending: boolean; error: Error | null; data?: { text: string } };
  intervention?: boolean;
}) {
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
        {state.isPending ? (
          <span className="text-muted-foreground animate-pulse">Generating…</span>
        ) : state.error ? (
          <span className="text-negative">{state.error.message}</span>
        ) : state.data ? (
          state.data.text || <span className="text-muted-foreground">(empty reply)</span>
        ) : (
          <span className="text-muted-foreground">Run a prompt to see the reply.</span>
        )}
      </div>
    </section>
  );
}
