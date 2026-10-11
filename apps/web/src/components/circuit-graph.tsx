"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";

import { part, partId } from "@/components/parts";
import type { CircuitLink } from "@/lib/api";
import { type Cut, layout, PAD, paths, type Placed } from "@/lib/circuit";
import { cn } from "@/lib/utils";

/** An attribution graph: token positions across, layers up, logits on top. Edges are green when
 * they push the target up and red when they push it down, wider for a larger share. Hovering or
 * picking a node lights its paths; arrow keys walk the graph. */
export function CircuitGraph({
  cut,
  tokens,
  selected,
  pinned,
  onSelect,
  onPin,
}: {
  cut: Cut;
  tokens: string[];
  selected: string | null;
  pinned: Set<string>;
  onSelect: (id: string | null) => void;
  onPin: (id: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const seen = new ResizeObserver(([e]) => setFit(Math.floor(e.contentRect.width)));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  const laid = useMemo(() => layout(cut, tokens, fit), [cut, tokens, fit]);
  const at = useMemo(() => new Map(laid.nodes.map((n) => [n.id, n])), [laid]);
  const [hover, setHover] = useState<string | null>(null);
  const focus = hover ?? (selected && at.has(selected) ? selected : null);
  const lit = useMemo(() => (focus ? paths(cut.links, focus) : null), [cut.links, focus]);
  const widest = Math.max(1e-9, ...cut.links.map((l) => l.share));

  const step = (from: Placed, key: string): Placed | undefined => {
    if (key === "ArrowUp" || key === "ArrowDown") {
      const up = key === "ArrowUp";
      const best = cut.links
        .filter((l) => (up ? l.source : l.target) === from.id)
        .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))[0];
      return best && at.get(up ? best.target : best.source);
    }
    const row = laid.nodes.filter((n) => n.y === from.y).sort((a, b) => a.x - b.x);
    return row[row.indexOf(from) + (key === "ArrowRight" ? 1 : -1)];
  };
  const tab =
    selected && at.has(selected)
      ? selected
      : (laid.nodes.find((n) => n.target) ?? laid.nodes[0])?.id;

  return (
    <div ref={box} className="overflow-x-auto rounded-xl border" {...part("circuits/canvas")}>
      <svg
        width={laid.width}
        height={laid.height}
        viewBox={`0 0 ${laid.width} ${laid.height}`}
        className="mx-auto block"
        role="group"
        aria-label="Attribution graph"
        onClick={(e) => e.target === e.currentTarget && onSelect(null)}
      >
        {laid.rows.map((r) => (
          <g key={r.y}>
            <line
              x1={PAD.left - 8}
              x2={laid.width - PAD.right}
              y1={r.y}
              y2={r.y}
              stroke="var(--border)"
              strokeDasharray="2 4"
            />
            <text
              x={PAD.left - 14}
              y={r.y}
              textAnchor="end"
              dominantBaseline="central"
              fontSize={11}
              className="fill-muted-foreground font-mono"
            >
              {r.kind === "logit" ? "out" : r.layer === "E" ? "emb" : `L${r.layer}`}
            </text>
          </g>
        ))}
        {laid.columns.map((c, i) => (
          <text
            key={i}
            transform={`translate(${c.x},${laid.height - PAD.bottom + 18}) rotate(-35)`}
            textAnchor="end"
            fontSize={11}
            className="fill-muted-foreground font-mono"
          >
            {JSON.stringify(c.token).slice(1, -1).slice(0, 14)}
          </text>
        ))}
        {cut.links.map((l) => (
          <Edge
            key={`${l.source}→${l.target}`}
            link={l}
            from={at.get(l.source)}
            to={at.get(l.target)}
            width={0.5 + 4 * Math.sqrt(l.share / widest)}
            dim={!!lit && !lit.links.has(l)}
            bright={!!lit?.links.has(l)}
          />
        ))}
        {laid.nodes.map((n) => (
          <Node
            key={n.id}
            n={n}
            on={n.id === selected}
            pinned={pinned.has(n.id)}
            dim={!!lit && !lit.nodes.has(n.id)}
            tabbable={n.id === tab}
            onSelect={() => onSelect(n.id)}
            onHover={(h) => setHover(h ? n.id : null)}
            onKey={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(n.id);
              } else if (e.key.toLowerCase() === "p" && !e.metaKey && !e.ctrlKey && !e.altKey) {
                e.preventDefault();
                onPin(n.id);
              } else if (e.key === "Escape") {
                onSelect(null);
              } else if (e.key.startsWith("Arrow")) {
                e.preventDefault();
                const next = step(n, e.key);
                if (next) {
                  onSelect(next.id);
                  document.getElementById(nodeDom(next.id))?.focus();
                }
              }
            }}
          />
        ))}
      </svg>
    </div>
  );
}

/** A logit's token ("Paris" from 'Output " Paris" (p=0.62)'), else the label cut to fit. */
function short(n: Placed): string {
  const text = n.kind === "logit" ? (n.label.match(/"(.*)"/)?.[1] ?? n.label) : n.label;
  return text.length > 18 ? `${text.slice(0, 17)}…` : text;
}

const nodeDom = (id: string) => `circuit-node-${id.replace(/[^\w-]/g, "_")}`;

const Edge = memo(function Edge({
  link,
  from,
  to,
  width,
  dim,
  bright,
}: {
  link: CircuitLink;
  from?: Placed;
  to?: Placed;
  width: number;
  dim: boolean;
  bright: boolean;
}) {
  if (!from || !to) return null;
  const mid = (from.y + to.y) / 2;
  return (
    <path
      d={`M${from.x},${from.y} C${from.x},${mid} ${to.x},${mid} ${to.x},${to.y}`}
      fill="none"
      stroke={link.weight >= 0 ? "var(--positive)" : "var(--negative)"}
      strokeWidth={width}
      strokeOpacity={dim ? 0.05 : bright ? 0.9 : 0.35}
      pointerEvents="none"
    />
  );
});

const Node = memo(function Node({
  n,
  on,
  pinned,
  dim,
  tabbable,
  onSelect,
  onHover,
  onKey,
}: {
  n: Placed;
  on: boolean;
  pinned: boolean;
  dim: boolean;
  tabbable: boolean;
  onSelect: () => void;
  onHover: (h: boolean) => void;
  onKey: (e: React.KeyboardEvent) => void;
}) {
  const shade = `color-mix(in oklch, var(--foreground) ${n.kind === "error" ? 25 : 35 + Math.round(55 * Math.min(1, n.r / 9))}%, var(--background))`;
  const stroke = on ? "var(--ring)" : pinned ? "var(--foreground)" : "var(--background)";
  const common = {
    fill: n.kind === "error" ? "var(--background)" : shade,
    stroke: n.kind === "error" && !on && !pinned ? "var(--muted-foreground)" : stroke,
    strokeWidth: on || pinned ? 2.5 : 1.25,
    strokeDasharray: n.kind === "error" ? "2 2" : undefined,
  };
  const r = n.r;
  return (
    <g
      id={nodeDom(n.id)}
      transform={`translate(${n.x},${n.y})`}
      role="button"
      tabIndex={tabbable ? 0 : -1}
      aria-pressed={on}
      aria-label={`${n.label}, ${n.kind}, layer ${n.layer}`}
      opacity={dim ? 0.2 : 1}
      className={cn(
        "cursor-pointer outline-none [&:focus-visible>*:first-child]:stroke-[var(--ring)]",
      )}
      onClick={onSelect}
      onFocus={onSelect}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onKeyDown={onKey}
      {...part(partId("circuits/node", n.id))}
    >
      {n.kind === "embedding" ? (
        <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={2} {...common} />
      ) : n.kind === "error" ? (
        <rect x={-r} y={-r} width={2 * r} height={2 * r} transform="rotate(45)" {...common} />
      ) : n.kind === "logit" ? (
        <path
          d={`M${-r - 3},${r} L${-r - 3},${-r + 3} L0,${-r - 3} L${r + 3},${-r + 3} L${r + 3},${r} Z`}
          {...common}
        />
      ) : (
        <circle r={r} {...common} />
      )}
      {(n.kind === "logit" || pinned) && (
        <text
          y={-r - 8}
          textAnchor="middle"
          fontSize={10}
          className="fill-foreground pointer-events-none font-mono"
        >
          {short(n)}
        </text>
      )}
      <title>{n.label}</title>
    </g>
  );
});
