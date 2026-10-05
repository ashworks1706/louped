"use client";

import { Help } from "@/components/help";
import { arrange, PartNote, part, partId, useRules } from "@/components/parts";
import { Figure } from "@/components/run-views";
import type { Result } from "@/components/save-result";
import { Input } from "@/components/ui/input";
import type { Direction, PlaygroundInfo, View } from "@/lib/api";
import { slug } from "@/lib/parts";

/** What the shared form sets for every tool: the model, its vectors and the intervention. */
export type Setup = {
  info: PlaygroundInfo;
  vectors: Direction[];
  vector?: Direction;
  layer: number;
  interventions: Record<string, unknown>[];
  live: string[];
  intervened: boolean;
  gen: { max_new_tokens: number; steps: number | null };
  /** The prompt last run, from the URL. */
  prompt: string;
  label: string;
};

/** A tool as the prompt form drives it: whether it can run, running it, whether it is still
 * busy, and what it showed to keep as a run (null until it has finished a result). */
export type Tool = {
  ready: boolean;
  busy: boolean;
  run: (prompt: string) => void;
  keep: () => Result | null;
};

/** What a computing route showed, to keep: the request it was sent and the figures it returned. */
export function kept(
  state: { data?: { views: View[] }; variables?: unknown },
  prompt: string,
  label: string,
): Result | null {
  if (!state.data || !state.variables) return null;
  const sent = state.variables as Record<string, unknown>;
  return {
    prompt: String(sent.prompt ?? sent.clean ?? prompt),
    settings: sent,
    label,
    views: state.data.views,
  };
}

/** One control with its label, a part a layout may hide, rename or put a note under; name is its
 * address when the label changes with the model. */
export function Field({
  label,
  name,
  help,
  children,
}: {
  label: string;
  name?: string;
  help?: string;
  children: React.ReactNode;
}) {
  const id = partId("playground/field", name ?? slug(label));
  const rule = useRules()(id);
  if (rule.hidden) return null;
  return (
    <div className="flex flex-col gap-1.5" {...part(id)}>
      <span className="text-muted-foreground inline-flex items-center gap-1 text-xs font-medium">
        {rule.label ?? label}
        {help && <Help label={`What is ${label}?`}>{rule.about ?? help}</Help>}
      </span>
      {children}
      <PartNote rule={rule} />
    </div>
  );
}

export function NumberField({
  label,
  value,
  min,
  max,
  onChange,
  help,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
  help?: string;
}) {
  return (
    <Field label={label} help={help}>
      <Input
        type="number"
        aria-label={label}
        value={value}
        min={min}
        max={max}
        step="any"
        onChange={(e) => {
          const v = Number(e.target.value);
          if (e.target.value === "" || !Number.isFinite(v)) return;
          onChange(Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v)));
        }}
        className="font-mono"
      />
    </Field>
  );
}

/** The figures a computing route returned, or why there are none. */
export function Views({
  state,
  empty,
}: {
  state: { isPending: boolean; error: Error | null; data?: { views: View[] }; submittedAt: number };
  empty: string;
}) {
  if (state.isPending)
    return <span className="text-muted-foreground animate-pulse text-sm">Running…</span>;
  if (state.error) return <span className="text-negative text-sm">{state.error.message}</span>;
  if (!state.data) return <span className="text-muted-foreground text-sm">{empty}</span>;
  return <ViewList views={state.data.views} at={state.submittedAt} />;
}

/** A tool's figures, each a part by its title that a layout may hide or put a note under. */
export function ViewList({ views, at }: { views: View[]; at: number }) {
  const rule = useRules();
  const id = (v: View) => partId("playground/figure", slug(v.title));
  return (
    <>
      {arrange(views, id, rule).map((v, i) => (
        <Figure key={`${at}-${i}`} view={v} id={id(v)} />
      ))}
    </>
  );
}
