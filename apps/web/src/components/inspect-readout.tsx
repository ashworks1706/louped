"use client";

import { parseAsInteger, parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useMemo, useState } from "react";

import { Help } from "@/components/help";
import { part, partId, PartNote, useRules } from "@/components/parts";
import { Term } from "@/components/term";
import { NativeSelect } from "@/components/ui/native-select";
import { Input } from "@/components/ui/input";
import { VegaFigure } from "@/components/vega-figure";
import type { Readout } from "@/lib/api";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

const METRICS = ["dla", "entropy", "prev", "first"] as const;
type Metric = (typeof METRICS)[number];
const METRIC_LABEL: Record<Metric, string> = {
  dla: "Logit attribution",
  entropy: "Entropy",
  prev: "Previous token",
  first: "First token",
};
const METRIC_ABOUT: Record<Metric, string> = {
  dla: "How much each head writes the target token at the picked position, straight to the output. Green pushes it up, red pushes it down.",
  entropy:
    "How spread out each head's attention is, averaged over positions. Low: it looks at one token.",
  prev: "The share of each head's attention on the token just before. A high one tracks position.",
  first:
    "The share of each head's attention on the first token, often a place to park attention it does not need.",
};

/** Where the person is looking: a position, a lens cell's layer, a head, a metric for the heads,
 * and the target (text, or "#<id>" for a token picked in the lens). Keys of their own: the Probe's
 * layer and heads are the intervention's. */
export function useReadoutState() {
  return useQueryStates({
    lpos: parseAsInteger,
    llayer: parseAsInteger,
    lhead: parseAsString,
    lmetric: parseAsStringLiteral(METRICS).withDefault("dla"),
    ltarget: parseAsString.withDefault(""),
  });
}

/** A target as the server takes it: a token id ("#123") or one token's text. */
export function targetOf(t: string): { target: string | null; target_id: number | null } {
  const id = /^#(\d+)$/.exec(t);
  return id ? { target: null, target_id: Number(id[1]) } : { target: t || null, target_id: null };
}

/** One forward pass read layer by layer, every panel at the picked token: what each layer would
 * say, where the target appears, which parts write it, and what each head does. With an
 * intervention, `other` is the base pass and each panel shows the change. */
export function InspectReadout({
  r,
  other,
  label,
  patterns,
  onTarget,
}: {
  r: Readout;
  other: Readout | null;
  label: string;
  patterns: Record<string, number[][]> | null;
  onTarget: (target: string) => void;
}) {
  const [s, set] = useReadoutState();
  const last = r.tokens.length - 1;
  const top = r.layers.length - 1;
  // a shared link can name a position or layer this prompt or model does not have
  const pos = Math.max(0, Math.min(s.lpos ?? last, last));
  const layer = Math.max(0, Math.min(s.llayer ?? top, top));
  const [draft, setDraft] = useState<string | null>(null);
  const word = r.vocab[String(r.target)] ?? "";
  const rank = r.target_rank[top][pos];
  const prob = r.target_prob[top][pos];
  const compare = other !== null && other.target === r.target ? other : null;
  const follow = (t: string) => {
    setDraft(null);
    onTarget(t);
  };
  const charts = useMemo(
    () => ({
      target: targetChart(r, compare, pos, label),
      certainty: certaintyChart(r, compare, pos, label),
      dla: dlaChart(r, compare, pos),
    }),
    [r, compare, pos, label],
  );

  return (
    <div className="flex flex-col gap-4" {...part("playground/readout")}>
      <div className="flex flex-col gap-2">
        <div
          role="listbox"
          aria-label="Token position"
          className="flex flex-wrap gap-0.5"
          {...part("playground/readout/tokens")}
          onKeyDown={(e) => {
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
            e.preventDefault();
            const next = Math.max(0, Math.min(last, pos + (e.key === "ArrowRight" ? 1 : -1)));
            void set({ lpos: next });
            document.getElementById(`readout-token-${next}`)?.focus();
          }}
        >
          {r.tokens.map((t, i) => (
            <button
              key={i}
              id={`readout-token-${i}`}
              type="button"
              role="option"
              aria-selected={i === pos}
              tabIndex={i === pos ? 0 : -1}
              onClick={() => void set({ lpos: i })}
              className={cn(
                "focus-visible:ring-ring rounded px-1 py-0.5 font-mono text-xs whitespace-pre outline-none focus-visible:ring-2",
                i === pos ? "bg-foreground text-background" : "bg-muted hover:bg-accent",
              )}
            >
              {show(t)}
            </button>
          ))}
        </div>
        <form
          className="flex flex-wrap items-center gap-2 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft !== null) follow(draft);
          }}
          {...part("playground/readout/target")}
        >
          <span className="text-muted-foreground flex items-center gap-1 text-xs">
            <label htmlFor="readout-target">Target</label>
            <Help label="What is the target?">
              The token every panel follows. By default the model&apos;s prediction at the last
              position; type one token and press Enter, or click a token in the lens&apos;s list.
            </Help>
          </span>
          <Input
            id="readout-target"
            value={draft ?? word}
            onChange={(e) => setDraft(e.target.value)}
            className="h-7 w-40 font-mono text-xs"
          />
          <span className="text-muted-foreground font-mono text-xs tabular-nums">
            at {pos} {JSON.stringify(r.tokens[pos])}: p = {num(prob, 3)}, rank {rank + 1}
          </span>
        </form>
        {other !== null && !compare && (
          <p className="text-muted-foreground text-xs">
            Base and the intervention follow different tokens, so the panels show this pass alone.
            Pick one target to compare them.
          </p>
        )}
      </div>

      <Lens
        r={r}
        other={compare}
        pos={pos}
        layer={layer}
        onPick={(p, l) => void set({ lpos: p, llayer: l })}
        onTarget={follow}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          id="target"
          title={`${JSON.stringify(word)} by layer`}
          about="The target token's probability (top) and rank (bottom, 1 is the top) if the model stopped after each layer, at the picked position. Where it jumps is where the answer forms."
        >
          <VegaFigure view={charts.target} />
        </Panel>
        <Panel
          id="certainty"
          title="Certainty by layer"
          about="Entropy: how unsure each layer's guess is (nats). KL: how far it is from the final answer (nats). Both fall to the right as the model settles."
        >
          <VegaFigure view={charts.certainty} />
        </Panel>
        <Panel
          id="dla"
          title="Who writes the target"
          about="Direct logit attribution: how much each layer's attention and MLP add to the target's logit at the picked position, straight to the output, with the final norm frozen. With the rest (the norm's and the head's biases), the bars add up to the logit before any softcap. With an intervention, the bars show the change from base."
        >
          <VegaFigure view={charts.dla} />
        </Panel>
        <Heads
          r={r}
          other={compare}
          pos={pos}
          metric={s.lmetric}
          head={s.lhead}
          patterns={patterns}
          onMetric={(lmetric) => void set({ lmetric })}
          onHead={(lhead) => void set({ lhead })}
        />
      </div>
    </div>
  );
}

const show = (t: string) => JSON.stringify(t).slice(1, -1) || " ";

function Panel({
  id,
  title,
  about,
  note,
  children,
}: {
  id: string;
  title: string;
  about: string;
  note?: React.ReactNode;
  children: React.ReactNode;
}) {
  const address = partId("playground/readout/panel", id);
  const rule = useRules()(address);
  if (rule.hidden) return null;
  return (
    <figure className="min-w-0 rounded-xl border" {...part(address)}>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          {title}
          <Help label={`How to read ${title}`}>{about}</Help>
        </span>
        {note}
        <PartNote rule={rule} className="basis-full" />
      </figcaption>
      <div className="p-4">{children}</div>
    </figure>
  );
}

/** Cell fill: grey by strength, or green and red for a signed value. */
function fill(v: number, signed: boolean): string {
  const a = Math.round(Math.min(1, Math.abs(v)) * 85);
  if (!signed) return `color-mix(in oklch, var(--foreground) ${a}%, var(--background))`;
  return `color-mix(in oklch, var(${v >= 0 ? "--positive" : "--negative"}) ${a}%, var(--background))`;
}

function Lens({
  r,
  other,
  pos,
  layer,
  onPick,
  onTarget,
}: {
  r: Readout;
  other: Readout | null;
  pos: number;
  layer: number;
  onPick: (pos: number, layer: number) => void;
  onTarget: (t: string) => void;
}) {
  const rows = r.layers.length;
  const cols = r.tokens.length;
  const [at, setAt] = useState<[number, number] | null>(null);
  const [l, p] = at ?? [layer, pos];
  const cell = Math.max(18, Math.min(56, Math.floor(880 / cols)));
  const labelled = cell >= 34;
  const delta = other !== null;
  const value = (li: number, pi: number) =>
    delta ? r.target_prob[li][pi] - other.target_prob[li][pi] : r.top_probs[li][pi][0];
  const move = (li: number, pi: number) => {
    const nl = Math.max(0, Math.min(rows - 1, li));
    const np = Math.max(0, Math.min(cols - 1, pi));
    onPick(np, nl);
    document.getElementById(`lens-${nl}-${np}`)?.focus();
  };
  return (
    <Panel
      id="lens"
      title="Logit lens"
      about={
        delta
          ? "Each cell: how much the intervention moved the target's probability if the model stopped after that layer (row) at that token (column). Green: up; red: down. Hover or focus a cell for its top tokens."
          : "Each cell: the top next token if the model stopped after that layer (row) at that token (column), shaded by its probability. Hover or focus a cell for its top 5; click one to follow it."
      }
      note={
        <span className="text-muted-foreground text-xs">
          {delta ? "Δ target probability" : "top token, by probability"}
        </span>
      }
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="overflow-x-auto">
          <div
            role="grid"
            aria-label="Logit lens: layers by token"
            className="inline-grid gap-px"
            style={{ gridTemplateColumns: `2.5rem repeat(${cols}, ${cell}px)` }}
            onMouseLeave={() => setAt(null)}
          >
            {[...r.layers.keys()].reverse().map((li) => (
              <div key={li} role="row" className="contents">
                <span className="text-muted-foreground self-center pr-1 text-right font-mono text-[10px]">
                  {r.layers[li] === "emb" ? "emb" : `L${r.layers[li]}`}
                </span>
                {r.tokens.map((_, pi) => {
                  const v = value(li, pi);
                  const top = r.vocab[String(r.top_ids[li][pi][0])] ?? "";
                  const on = pi === pos && li === layer;
                  return (
                    <button
                      key={pi}
                      id={`lens-${li}-${pi}`}
                      type="button"
                      role="gridcell"
                      aria-selected={on}
                      aria-label={`layer ${r.layers[li]}, token ${pi}: ${top} ${num(r.top_probs[li][pi][0], 2)}`}
                      tabIndex={on ? 0 : -1}
                      data-testid="lens-cell"
                      onMouseEnter={() => setAt([li, pi])}
                      onFocus={() => setAt([li, pi])}
                      onClick={() => onPick(pi, li)}
                      onKeyDown={(e) => {
                        const d = {
                          ArrowUp: [1, 0],
                          ArrowDown: [-1, 0],
                          ArrowLeft: [0, -1],
                          ArrowRight: [0, 1],
                        }[e.key];
                        if (!d) return;
                        e.preventDefault();
                        move(li + d[0], pi + d[1]);
                      }}
                      className={cn(
                        "focus-visible:ring-ring h-6 overflow-hidden px-0.5 font-mono text-[10px] leading-6 outline-none focus-visible:ring-2",
                        pi === pos && "ring-foreground/40 ring-1",
                        on && "ring-foreground ring-2",
                        Math.abs(v) > 0.62 && !delta ? "text-background" : "text-foreground",
                      )}
                      style={{ background: fill(delta ? v * 2 : v, delta) }}
                    >
                      {labelled ? show(top) : ""}
                    </button>
                  );
                })}
              </div>
            ))}
            <div role="row" className="contents">
              <span />
              {r.tokens.map((t, pi) => (
                <span
                  key={pi}
                  role="columnheader"
                  className={cn(
                    "truncate pt-1 text-center font-mono text-[10px]",
                    pi === pos ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {show(t)}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div
          className="flex flex-col gap-1 text-xs"
          aria-live="polite"
          {...part("playground/readout/cell")}
        >
          <span className="text-muted-foreground">
            layer {r.layers[l]} · token {p} {JSON.stringify(r.tokens[p])}
          </span>
          <ol>
            {r.top_ids[l][p].map((id, k) => (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onTarget(`#${id}`)}
                  title="Follow this token"
                  className={cn(
                    "hover:bg-muted focus-visible:ring-ring flex w-full items-center gap-2 rounded px-1 py-0.5 text-left outline-none focus-visible:ring-2",
                    id === r.target && "font-medium",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate font-mono">
                    {JSON.stringify(r.vocab[String(id)] ?? "")}
                  </span>
                  <span className="bg-muted relative h-1.5 w-16 overflow-hidden rounded">
                    <span
                      className="bg-foreground absolute inset-y-0 left-0"
                      style={{ width: `${r.top_probs[l][p][k] * 100}%` }}
                    />
                  </span>
                  <span className="w-10 text-right font-mono tabular-nums">
                    {num(r.top_probs[l][p][k], 3)}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <span className="text-muted-foreground flex gap-3 font-mono tabular-nums">
            <Term k="entropy">entropy {num(r.entropy[l][p], 2)}</Term>
            <Term k="kl_final">KL {num(r.kl[l][p], 2)}</Term>
          </span>
        </div>
      </div>
    </Panel>
  );
}

const layerName = (l: string) => (l === "emb" ? "emb" : `L${l}`);

function targetChart(r: Readout, other: Readout | null, pos: number, label: string) {
  const rows = (x: Readout, side: string) =>
    x.layers.map((l, i) => ({
      layer: layerName(l),
      i,
      side,
      p: x.target_prob[i][pos],
      rank: x.target_rank[i][pos] + 1,
    }));
  const values = [...rows(r, other ? label : "this pass"), ...(other ? rows(other, "base") : [])];
  return vega("target", values, {
    vconcat: [
      {
        height: 120,
        width: "container",
        mark: { type: "line", point: true },
        encoding: {
          x: { field: "layer", type: "ordinal", sort: { field: "i" }, title: null },
          y: { field: "p", type: "quantitative", title: "probability", scale: { domain: [0, 1] } },
          ...sides(other, label),
          tooltip: [{ field: "side" }, { field: "layer" }, { field: "p", format: ".3f" }],
        },
      },
      {
        height: 90,
        width: "container",
        mark: { type: "line", point: true },
        encoding: {
          x: { field: "layer", type: "ordinal", sort: { field: "i" }, title: "layer" },
          y: {
            field: "rank",
            type: "quantitative",
            title: "rank",
            scale: { type: "log", reverse: true },
          },
          ...sides(other, label),
          tooltip: [{ field: "side" }, { field: "layer" }, { field: "rank" }],
        },
      },
    ],
  });
}

function certaintyChart(r: Readout, other: Readout | null, pos: number, label: string) {
  const rows = (x: Readout, side: string) =>
    x.layers.flatMap((l, i) => [
      { layer: layerName(l), i, side, measure: "entropy", v: x.entropy[i][pos] },
      { layer: layerName(l), i, side, measure: "KL to final", v: x.kl[i][pos] },
    ]);
  const values = [...rows(r, other ? label : "this pass"), ...(other ? rows(other, "base") : [])];
  return vega("certainty", values, {
    height: 230,
    mark: { type: "line", point: true },
    encoding: {
      x: { field: "layer", type: "ordinal", sort: { field: "i" }, title: "layer" },
      y: { field: "v", type: "quantitative", title: "nats" },
      strokeDash: { field: "measure", title: null },
      ...sides(other, label),
      tooltip: [
        { field: "side" },
        { field: "measure" },
        { field: "layer" },
        { field: "v", format: ".3f" },
      ],
    },
  });
}

function dlaChart(r: Readout, other: Readout | null, pos: number) {
  const parts = (x: Readout) => [
    { layer: "emb", i: 0, part: "embed", v: x.dla_embed[pos] },
    ...x.layers.slice(1).flatMap((l, i) => [
      { layer: `L${l}`, i: i + 1, part: "attention", v: x.dla_attn[i][pos] },
      { layer: `L${l}`, i: i + 1, part: "MLP", v: x.dla_mlp[i][pos] },
    ]),
  ];
  const mine = parts(r);
  const base = other ? parts(other) : null;
  const values = mine.map((m, k) => ({
    ...m,
    shade: m.part === "attention" ? "attention" : "MLP",
    v: base ? m.v - base[k].v : m.v,
  }));
  return vega("dla", values, {
    height: 230,
    mark: { type: "bar" },
    encoding: {
      x: { field: "layer", type: "ordinal", sort: { field: "i" }, title: "layer" },
      xOffset: { field: "part" },
      y: {
        field: "v",
        type: "quantitative",
        title: other ? "Δ logit" : "logit",
        axis: { format: ".3~f" },
      },
      // the theme's category colours are [ink, intervention, muted]: attention in ink, the MLP
      // and the embeddings muted, the intervention colour unused
      color: {
        field: "shade",
        title: null,
        scale: { domain: ["attention", "-", "MLP"] },
        legend: { orient: "top", values: ["attention", "MLP"] },
      },
      tooltip: [
        { field: "layer" },
        { field: "part" },
        { field: "v", format: ".3f", title: other ? "Δ logit" : "logit" },
      ],
    },
  });
}

/** One line per pass: this pass in ink, or the intervention in its colour beside base, muted (the
 * theme's category colours are [ink, intervention, muted]). */
function sides(other: Readout | null, label: string) {
  return {
    color: {
      field: "side",
      title: null,
      scale: { domain: other ? ["this pass", label, "base"] : ["this pass"] },
      legend: other ? { orient: "top", values: [label, "base"] } : null,
    },
  };
}

function vega(id: string, values: object[], spec: object) {
  return {
    kind: "vega" as const,
    title: id,
    spec: { data: { values }, ...spec },
    items: null,
  };
}

function Heads({
  r,
  other,
  pos,
  metric,
  head,
  patterns,
  onMetric,
  onHead,
}: {
  r: Readout;
  other: Readout | null;
  pos: number;
  metric: Metric;
  head: string | null;
  patterns: Record<string, number[][]> | null;
  onMetric: (m: Metric) => void;
  onHead: (h: string) => void;
}) {
  const layers = r.dla_heads.length;
  const heads = r.head_entropy[0]?.length ?? 0;
  const col = r.head_positions.indexOf(pos);
  const at = col >= 0 ? col : r.head_positions.length - 1;
  const read = (x: Readout, l: number, h: number) =>
    metric === "dla"
      ? x.dla_heads[l][h][at]
      : metric === "entropy"
        ? x.head_entropy[l][h]
        : metric === "prev"
          ? x.head_prev[l][h]
          : x.head_first[l][h];
  const grid = useMemo(
    () =>
      Array.from({ length: layers }, (_, l) =>
        Array.from({ length: heads }, (_, h) => read(r, l, h) - (other ? read(other, l, h) : 0)),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [r, other, metric, at, layers, heads],
  );
  const signed = metric === "dla" || other !== null;
  const scale = Math.max(1e-9, ...grid.flat().map(Math.abs));
  const [hl, hh] = (head ?? "").split(".").map(Number);
  const picked =
    Number.isInteger(hl) && Number.isInteger(hh) && hl < layers && hh < heads ? [hl, hh] : null;
  const weights =
    picked && patterns ? patterns[`layer ${picked[0]} · head ${picked[1]}`]?.[pos] : undefined;
  const cell = Math.max(10, Math.min(28, Math.floor(420 / heads)));
  const [fl, fh] = picked ?? [0, 0];
  const step = (l: number, h: number) => {
    const nl = Math.max(0, Math.min(layers - 1, l));
    const nh = Math.max(0, Math.min(heads - 1, h));
    onHead(`${nl}.${nh}`);
    document.getElementById(`head-${nl}-${nh}`)?.focus();
  };
  return (
    <Panel
      id="heads"
      title="Heads"
      about={`${METRIC_ABOUT[metric]}${other ? " With an intervention, the change from base." : ""} Click a head to see what the picked token reads through it.`}
      note={
        <NativeSelect
          aria-label="Score heads by"
          value={metric}
          onChange={(e) => onMetric(e.target.value as Metric)}
          className="h-7 w-auto text-xs"
          {...part("playground/readout/heads-metric")}
        >
          {METRICS.map((m) => (
            <option key={m} value={m}>
              {METRIC_LABEL[m]}
            </option>
          ))}
        </NativeSelect>
      }
    >
      <div className="flex flex-col gap-3">
        {metric === "dla" && col < 0 && (
          <p className="text-muted-foreground text-xs">
            Shown at the last token: this prompt is too long to attribute every head at every token.
          </p>
        )}
        <div className="overflow-x-auto">
          <div
            className="inline-grid gap-px"
            style={{ gridTemplateColumns: `2.5rem repeat(${heads}, ${cell}px)` }}
            role="grid"
            aria-label="Heads: layers by head"
          >
            {grid.map((row, l) => (
              <div key={l} role="row" className="contents">
                <span className="text-muted-foreground pr-1 text-right font-mono text-[10px] leading-4">
                  L{l}
                </span>
                {row.map((v, h) => {
                  const on = picked?.[0] === l && picked?.[1] === h;
                  return (
                    <button
                      key={h}
                      id={`head-${l}-${h}`}
                      type="button"
                      role="gridcell"
                      aria-selected={on}
                      tabIndex={l === fl && h === fh ? 0 : -1}
                      onKeyDown={(e) => {
                        const d = {
                          ArrowUp: [-1, 0],
                          ArrowDown: [1, 0],
                          ArrowLeft: [0, -1],
                          ArrowRight: [0, 1],
                        }[e.key];
                        if (!d) return;
                        e.preventDefault();
                        step(l + d[0], h + d[1]);
                      }}
                      aria-label={`layer ${l} head ${h}: ${num(v, 3)}`}
                      title={`L${l}.H${h}: ${num(v, 3)}`}
                      data-testid="head-cell"
                      onClick={() => onHead(`${l}.${h}`)}
                      className={cn(
                        "focus-visible:ring-ring h-4 outline-none focus-visible:ring-2",
                        on && "ring-foreground ring-2",
                      )}
                      style={{ background: fill(v / scale, signed) }}
                    />
                  );
                })}
              </div>
            ))}
            <div role="row" className="contents">
              <span />
              {Array.from({ length: heads }, (_, h) => (
                <span
                  key={h}
                  role="columnheader"
                  className="text-muted-foreground text-center font-mono text-[10px]"
                >
                  {heads <= 16 || h % 4 === 0 ? h : ""}
                </span>
              ))}
            </div>
          </div>
        </div>
        {picked && (
          <div className="flex flex-col gap-1" {...part("playground/readout/head")}>
            <span className="text-muted-foreground text-xs">
              L{picked[0]}.H{picked[1]} from token {pos} {JSON.stringify(r.tokens[pos])}: entropy{" "}
              {num(r.head_entropy[picked[0]][picked[1]], 2)}, previous{" "}
              {num(r.head_prev[picked[0]][picked[1]], 2)}, first{" "}
              {num(r.head_first[picked[0]][picked[1]], 2)}
            </span>
            {weights ? (
              <p className="leading-6">
                {r.tokens.map((t, i) => (
                  <span
                    key={i}
                    title={i <= pos ? num(weights[i], 3) : undefined}
                    className="rounded-sm font-mono text-xs whitespace-pre"
                    style={{
                      background: i <= pos ? fill(weights[i], false) : undefined,
                      color: (weights[i] ?? 0) > 0.62 ? "var(--background)" : undefined,
                    }}
                  >
                    {show(t)}
                  </span>
                ))}
              </p>
            ) : (
              <p className="text-muted-foreground text-xs">No attention weights for this pass.</p>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}
