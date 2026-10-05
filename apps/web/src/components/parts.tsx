"use client";

import { createContext, useContext, useEffect } from "react";

import { useLayout } from "@/components/layout";
import { Markdown } from "@/components/markdown";
import type { PartRule } from "@/lib/api";
import { part } from "@/lib/parts";
export { part, partId } from "@/lib/parts";
import { cn } from "@/lib/utils";

/** Which experiment's layout a page's parts follow: a run's page and an experiment's page set it;
 * elsewhere the project's. */
const Scope = createContext<string | null>(null);
export const PartScope = ({
  experiment,
  children,
}: {
  experiment: string | null | undefined;
  children: React.ReactNode;
}) => <Scope.Provider value={experiment ?? null}>{children}</Scope.Provider>;

const wildcards = (key: string) => key.split("/").filter((s) => s === "*").length;
function matches(key: string, id: string) {
  const want = key.split("/");
  const got = id.split("/");
  return want.length === got.length && want.every((w, i) => w === "*" || w === got[i]);
}

/** The rules in force for one address: every matching key, the more specific (fewer *) over the
 * broader. */
export function ruleFor(rules: Record<string, PartRule> | undefined, id: string): Rule {
  if (!rules) return {};
  return Object.keys(rules)
    .filter((k) => matches(k, id))
    .sort((a, b) => wildcards(b) - wildcards(a))
    .reduce<Rule>((got, k) => ({ ...got, ...setOnly(rules[k]) }), {});
}
/** A rule's set fields: hidden false is the default, not a rule that shows a part a broader key
 * hides. */
const setOnly = (r: PartRule): Rule =>
  Object.fromEntries(
    Object.entries(r).filter(([, v]) => v !== null && v !== undefined && v !== false),
  );

/** What the layout changes about one part; unset fields keep the app's own. */
export type Rule = Partial<PartRule>;

/** The layout's part rules as a lookup, for components that draw many parts. */
export function useRules(): (id: string) => Rule {
  const experiment = useContext(Scope);
  const layout = useLayout(experiment);
  const rules = layout.data?.parts;
  return (id) => ruleFor(rules, id);
}

/** Siblings as the layout orders them: hidden ones out, those with an order first by it, the rest
 * after in their own order. */
export function arrange<T>(items: T[], idOf: (t: T) => string, rule: (id: string) => Rule) {
  return items
    .map((t, i) => ({ t, i, r: rule(idOf(t)) }))
    .filter((x) => !x.r.hidden)
    .sort((a, b) => (a.r.order ?? Infinity) - (b.r.order ?? Infinity) || a.i - b.i)
    .map((x) => x.t);
}

/** A part's note from the layout: Markdown under it. */
export function PartNote({ rule, className }: { rule: Rule; className?: string }) {
  if (!rule.note) return null;
  return (
    <div className={cn("text-muted-foreground text-xs [&_p]:my-0", className)}>
      <Markdown noImages>{rule.note}</Markdown>
    </div>
  );
}

/** What a picked part stands for, beyond its text: a component that draws parts registers how
 * to read them by address prefix, and Shift+click asks the longest prefix that matches. */
type Resolve = (id: string) => unknown;
const resolvers = new Map<string, Resolve>();

export function usePartData(prefix: string, resolve: Resolve) {
  useEffect(() => {
    resolvers.set(prefix, resolve);
    return () => {
      if (resolvers.get(prefix) === resolve) resolvers.delete(prefix);
    };
  }, [prefix, resolve]);
}

/** usePartData as an element, for a component whose parts are drawn after an early return. */
export function PartData({ prefix, resolve }: { prefix: string; resolve: Resolve }) {
  usePartData(prefix, resolve);
  return null;
}

export function partData(id: string): unknown {
  const prefix = [...resolvers.keys()]
    .filter((p) => id === p || id.startsWith(`${p}/`))
    .sort((a, b) => b.length - a.length)[0];
  return prefix ? (resolvers.get(prefix)!(id) ?? null) : null;
}

/** A part a layout may hide or put a note under: a section, a card, a group of controls. */
export function Part({
  id,
  className,
  children,
  as: As = "div",
}: {
  id: string;
  className?: string;
  children: React.ReactNode;
  as?: "div" | "section" | "header";
}) {
  const rule = useRules()(id);
  if (rule.hidden) return null;
  return (
    <As {...part(id)} className={className}>
      {children}
      <PartNote rule={rule} />
    </As>
  );
}
