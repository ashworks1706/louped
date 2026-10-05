"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseAsBoolean, parseAsInteger, useQueryState } from "nuqs";
import { useEffect } from "react";

import { Help } from "@/components/help";
import { Part, part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { abPick, q, type AbResult, type AbSession } from "@/lib/api";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

type Side = "left" | "right" | "tie";
const KEYS: Record<string, Side> = { "1": "left", "2": "right", "0": "tie" };

/** Opens a blind A/B of two eval runs: the person picks the better answer of each pair without
 * being told which run gave it, and sees what the picks say once they reveal. */
export function BlindButton() {
  const [, setOpen] = useQueryState("blind", parseAsBoolean);
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => void setOpen(true)}
        {...part("compare/blind/open")}
      >
        Blind A/B
      </Button>
      <Help label="What does Blind A/B do?">
        You pick the better answer of each pair without seeing which run gave it; the sides are
        shuffled once and kept. Reveal shows B&apos;s win rate with its 95% interval and how far any
        judge of the same runs agrees with you.
      </Help>
    </>
  );
}

export function BlindSheet({ a, b }: { a: string; b: string }) {
  const [open, setOpen] = useQueryState("blind", parseAsBoolean);
  return (
    <Sheet open={open === true} onOpenChange={(o) => !o && void setOpen(null)}>
      <SheetContent className="sm:max-w-5xl">
        <div className="border-b px-6 py-4">
          <SheetTitle className="font-semibold">Blind A/B</SheetTitle>
          <SheetDescription className="text-muted-foreground text-sm">
            Which answer is better? Keys: <Kbd>1</Kbd> left, <Kbd>2</Kbd> right, <Kbd>0</Kbd> tie,{" "}
            <Kbd>←</Kbd> <Kbd>→</Kbd> to move.
          </SheetDescription>
        </div>
        {open && <Pairs a={a} b={b} />}
      </SheetContent>
    </Sheet>
  );
}

function Pairs({ a, b }: { a: string; b: string }) {
  const session = useQuery(q.ab(a, b));
  return <QueryState query={session}>{(s) => <Picking a={a} b={b} s={s} />}</QueryState>;
}

function Picking({ a, b, s }: { a: string; b: string; s: AbSession }) {
  const client = useQueryClient();
  const [at, setAt] = useQueryState("pair", parseAsInteger);
  const [reveal, setReveal] = useQueryState("reveal", parseAsBoolean);
  const n = s.pairs.length;
  const firstOpen = s.pairs.findIndex((p) => p.pick == null);
  const i = Math.min(Math.max(at ?? (firstOpen < 0 ? 0 : firstOpen), 0), Math.max(n - 1, 0));
  const pair = s.pairs[i];
  // revealed, the picks are locked: a pick changed while the counts show would give its side away
  const choose = useMutation({
    mutationFn: (side: Side | null) => abPick({ a, b, sample: pair.sample, side }),
    meta: { action: "Pick" },
    onSuccess: (next) => {
      client.setQueryData(q.ab(a, b).queryKey, next);
      void client.invalidateQueries({ queryKey: ["ab-result", a, b] });
      const after = next.pairs.findIndex((p, k) => k > i && p.pick == null);
      const any = next.pairs.findIndex((p) => p.pick == null);
      void setAt(after >= 0 ? after : any >= 0 ? any : i);
    },
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || !pair || choose.isPending) return;
      if (e.target instanceof HTMLElement && ["INPUT", "TEXTAREA"].includes(e.target.tagName))
        return;
      if (KEYS[e.key] && !reveal) choose.mutate(KEYS[e.key]);
      else if (e.key === "ArrowRight") void setAt(Math.min(i + 1, n - 1));
      else if (e.key === "ArrowLeft") void setAt(Math.max(i - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [choose, pair, i, n, setAt, reveal]);
  if (n === 0)
    return (
      <p className="text-muted-foreground px-6 py-5 text-sm">
        These two runs share no sample both answered without error.
      </p>
    );
  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div
        className="flex items-center gap-3 border-b px-6 py-3 text-sm"
        {...part("compare/blind/progress")}
      >
        <span className="font-mono text-xs">
          {i + 1} / {n}
        </span>
        <span className="text-muted-foreground font-mono text-xs">{s.labelled} picked</span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => void setAt(i - 1)}>
            Back
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={i === n - 1}
            onClick={() => void setAt(i + 1)}
          >
            Next
          </Button>
          <Button
            size="sm"
            variant={reveal ? "default" : "outline"}
            disabled={!reveal && s.labelled < n}
            title={s.labelled < n ? "Pick every pair first" : undefined}
            onClick={() => void setReveal(reveal ? null : true)}
            {...part("compare/blind/reveal")}
          >
            {reveal ? "Hide result" : "Reveal"}
          </Button>
        </div>
      </div>
      {reveal && <Result a={a} b={b} />}
      <div className="flex flex-col gap-4 px-6 py-5">
        <Part id={partId("compare/blind/request", pair.sample)} className="flex flex-col gap-1">
          <span className="text-muted-foreground font-mono text-xs">sample {pair.sample}</span>
          <p className="max-h-48 overflow-y-auto text-sm whitespace-pre-wrap">{pair.request}</p>
        </Part>
        <div className="grid gap-4 md:grid-cols-2">
          {(["left", "right"] as const).map((side, k) => (
            <button
              key={side}
              type="button"
              onClick={() => choose.mutate(side)}
              disabled={choose.isPending || !!reveal}
              aria-pressed={pair.pick === side}
              className={cn(
                "hover:border-foreground/40 flex min-w-0 flex-col gap-2 rounded-lg border p-4 text-left transition-colors",
                pair.pick === side && "border-foreground",
              )}
              {...part(partId("compare/blind/side", side))}
            >
              <span className="flex items-center gap-2 text-xs">
                <Kbd>{k + 1}</Kbd>
                <span className="text-muted-foreground">{side === "left" ? "Left" : "Right"}</span>
              </span>
              <span className="text-sm whitespace-pre-wrap">{pair[side]}</span>
            </button>
          ))}
        </div>
        <div className="flex justify-center gap-2">
          <Button
            size="sm"
            variant={pair.pick === "tie" ? "default" : "outline"}
            onClick={() => choose.mutate("tie")}
            disabled={choose.isPending || !!reveal}
            {...part("compare/blind/tie")}
          >
            <Kbd>0</Kbd> Tie
          </Button>
          {pair.pick && !reveal && (
            <Button size="sm" variant="ghost" onClick={() => choose.mutate(null)}>
              Clear
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function Result({ a, b }: { a: string; b: string }) {
  const result = useQuery(q.abResult(a, b));
  return <QueryState query={result}>{(r) => <Revealed r={r} />}</QueryState>;
}

function Revealed({ r }: { r: AbResult }) {
  return (
    <Part id="compare/blind/result" className="flex flex-col gap-3 border-b px-6 py-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <span className="text-sm">
          B wins{" "}
          <span className="font-mono text-base font-medium">
            {r.b_rate == null ? "—" : pct(r.b_rate)}
          </span>
        </span>
        <span className="text-muted-foreground font-mono text-xs">
          {r.low != null && r.high != null ? `95%: ${pct(r.low)} to ${pct(r.high)}` : "n too small"}
        </span>
        <span className="text-muted-foreground font-mono text-xs">
          A {r.a_wins} · B {r.b_wins} · tie {r.ties} · {r.labelled}/{r.total} picked
        </span>
      </div>
      {r.judges.map((j) => (
        <div
          key={j.run}
          className="text-muted-foreground flex gap-4 font-mono text-xs"
          {...part(partId("compare/blind/judge", j.run))}
        >
          <span>judge {j.run}</span>
          <span>
            agrees {j.agreement == null ? "—" : pct(j.agreement)} of {j.labelled}
          </span>
          <span>κ {j.kappa == null ? "—" : num(j.kappa)}</span>
        </div>
      ))}
    </Part>
  );
}
