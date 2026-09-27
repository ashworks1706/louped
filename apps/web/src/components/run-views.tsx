"use client";

import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { QueryState } from "@/components/query-state";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  q,
  type HeatmapView,
  type LineView,
  type TableView,
  type TokensView,
  type View,
} from "@/lib/api";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Every figure a run logged under views/, in file order. */
export function RunViews({ id }: { id: string }) {
  const views = useQuery(q.views(id));
  return (
    <QueryState query={views}>
      {(all) => (
        <div className="flex flex-col gap-6">
          {all.map((v) => (
            <Figure key={v.path} view={v.view} />
          ))}
        </div>
      )}
    </QueryState>
  );
}

/** One figure of any kind, with its title and note. */
export function Figure({ view }: { view: View }) {
  return (
    <figure className="rounded-xl border">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-3">
        <span className="text-sm font-medium">{view.title}</span>
        {view.note && <span className="text-muted-foreground text-xs">{view.note}</span>}
      </figcaption>
      <div className="p-4">
        {view.kind === "line" && <LineFigure view={view} />}
        {view.kind === "heatmap" && <HeatmapFigure view={view} />}
        {view.kind === "table" && <TableFigure view={view} />}
        {view.kind === "tokens" && <TokensFigure view={view} />}
      </div>
    </figure>
  );
}

const STROKES = ["var(--foreground)", "var(--intervention)", "var(--muted-foreground)"];

function LineFigure({ view }: { view: LineView }) {
  const names = Object.keys(view.series);
  const data = view.x.map((x, i) =>
    Object.fromEntries([["x", x], ...names.map((n) => [n, view.series[n][i]])]),
  );
  const axis = { fontSize: 11, fill: "var(--muted-foreground)" };
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="x"
            tick={axis}
            tickLine={false}
            axisLine={false}
            label={{ value: view.x_label, position: "insideBottom", offset: -12, ...axis }}
          />
          <YAxis
            tick={axis}
            tickLine={false}
            axisLine={false}
            width={56}
            label={{ value: view.y_label, angle: -90, position: "insideLeft", ...axis }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--popover)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(v) => (typeof v === "number" ? v.toFixed(3) : String(v))}
            labelFormatter={(x) => `${view.x_label} ${x}`}
          />
          <Legend
            verticalAlign="top"
            height={28}
            iconType="plainline"
            wrapperStyle={{ fontSize: 12 }}
          />
          {names.map((n, i) => (
            <Line
              key={n}
              type="monotone"
              dataKey={n}
              stroke={STROKES[i % STROKES.length]}
              strokeWidth={1.5}
              strokeDasharray={i >= STROKES.length ? "4 3" : undefined}
              dot={{ r: 2 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** A signed colour: positive shades one way, negative the other, strength by magnitude. */
function shade(v: number, max: number) {
  const c = `color-mix(in oklch, var(${v >= 0 ? "--positive" : "--negative"}) ${Math.round(
    Math.min(1, Math.abs(v) / max) * 100,
  )}%, transparent)`;
  return `linear-gradient(${c}, ${c})`;
}

function Scale({ max }: { max: number }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="font-mono">−{max.toFixed(2)}</span>
      <span
        className="h-2 w-24 rounded-full"
        style={{
          background: "linear-gradient(to right, var(--negative), transparent, var(--positive))",
        }}
      />
      <span className="font-mono">+{max.toFixed(2)}</span>
    </span>
  );
}

function SeriesSelect({
  label,
  names,
  value,
  onChange,
}: {
  label: string;
  names: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  if (names.length < 2) return null;
  return (
    <NativeSelect
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="font-mono text-xs"
    >
      {names.map((n) => (
        <option key={n} value={n}>
          {n}
        </option>
      ))}
    </NativeSelect>
  );
}

/** Signed values: positive shades one way, negative the other, strength by magnitude. With
 * slices (attention: one per layer and head), a select picks which grid is drawn. */
function HeatmapFigure({ view }: { view: HeatmapView }) {
  const [hover, setHover] = useState<[number, number] | null>(null);
  const names = Object.keys(view.slices ?? {});
  const [slice, setSlice] = useState(names[0]);
  const z = view.slices?.[slice] ?? view.z;
  const labels = view.labels;
  const max = Math.max(1e-9, ...z.flat().map(Math.abs));
  const at = (r: number, c: number) =>
    `${view.y_label} ${view.y[r]}, ${view.x[c]}: ${labels ? `${JSON.stringify(labels[r][c])} ` : ""}${z[r][c].toFixed(3)}`;
  return (
    <div className="flex flex-col gap-3">
      <SeriesSelect label="Slice" names={names} value={slice} onChange={setSlice} />
      <div className="overflow-x-auto">
        <div
          className="grid w-max gap-px text-[10px]"
          style={{
            gridTemplateColumns: `auto repeat(${view.x.length}, minmax(${labels ? 48 : 28}px, 1fr))`,
          }}
          onMouseLeave={() => setHover(null)}
        >
          {view.y.map((y, r) => (
            <Fragment key={y}>
              <span className="text-muted-foreground pr-2 text-right font-mono leading-6">{y}</span>
              {view.x.map((x, c) => (
                <span
                  key={x}
                  data-testid="heat-cell"
                  className="bg-muted h-6 max-w-24 truncate rounded-[2px] px-1 font-mono leading-6 whitespace-pre outline-offset-1 hover:outline hover:outline-1"
                  style={{ backgroundImage: shade(z[r][c], max) }}
                  onMouseEnter={() => setHover([r, c])}
                  title={at(r, c)}
                >
                  {labels?.[r][c]}
                </span>
              ))}
            </Fragment>
          ))}
          <span />
          {view.x.map((x) => (
            <span
              key={x}
              className="text-muted-foreground h-16 truncate pt-1 font-mono [writing-mode:vertical-rl]"
              title={x}
            >
              {x}
            </span>
          ))}
        </div>
      </div>
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span>
          rows {view.y_label} · columns {view.x_label}
        </span>
        <Scale max={max} />
        <span className="text-foreground font-mono tabular-nums" aria-live="polite">
          {hover ? at(hover[0], hover[1]) : " "}
        </span>
      </div>
    </div>
  );
}

/** Text coloured per token by the chosen series; each text takes focus, and arrow keys move a
 * cursor that reads out the token under it. With pairs (attention), the colour is the query
 * token's row of the chosen grid (the hovered token, a picked one, or the last) and the grid
 * itself is drawn below. */
function TokensFigure({ view }: { view: TokensView }) {
  const names = Object.keys(view.rows[0]?.values ?? {});
  const [picked, setSeries] = useState(names[0]);
  const series = names.includes(picked) ? picked : names[0];
  const [hover, setHover] = useState<[number, number] | null>(null);
  const [lockedAt, setLocked] = useState<number | null>(null);
  const grid = view.pairs?.[series];
  const locked = grid && lockedAt !== null && lockedAt < grid.length ? lockedAt : null;
  const query = grid ? (locked ?? hover?.[1] ?? grid.length - 1) : null;
  const values = (r: number) =>
    grid && query !== null ? grid[query] : view.rows[r].values[series];
  const max = Math.max(1e-9, ...view.rows.flatMap((_, r) => values(r).map(Math.abs)));
  const token = (r: number, i: number) => `${i} ${JSON.stringify(view.rows[r].tokens[i])}`;
  const toggle = (i: number) => setLocked(locked === i ? null : i);
  const readout = !hover
    ? grid && locked !== null
      ? `query ${token(0, locked)} picked; pick it again to release`
      : " "
    : grid && locked === null
      ? `query ${token(0, hover[1])}; click or press Enter to pick`
      : `${token(hover[0], hover[1])}: ${values(hover[0])[hover[1]].toFixed(3)}`;
  const keys = (r: number) => (e: React.KeyboardEvent) => {
    const n = view.rows[r].tokens.length;
    const at = hover?.[0] === r ? hover[1] : n - 1;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      setHover([r, Math.min(n - 1, Math.max(0, at + (e.key === "ArrowLeft" ? -1 : 1)))]);
    } else if (grid && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      toggle(at);
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <SeriesSelect label="Series" names={names} value={series} onChange={setSeries} />
      <div className="flex flex-col gap-2" onMouseLeave={() => setHover(null)}>
        {view.rows.map((row, r) => (
          <div key={r} className="flex flex-col gap-1">
            {row.label && (
              <span className="text-muted-foreground font-mono text-[11px]">{row.label}</span>
            )}
            <p
              tabIndex={0}
              aria-label={`${row.label ?? "text"}: arrow keys move between tokens`}
              onKeyDown={keys(r)}
              onFocus={() => setHover([r, row.tokens.length - 1])}
              onBlur={() => setHover(null)}
              className="focus-visible:ring-ring/40 rounded-sm font-mono text-xs leading-6 break-all whitespace-pre-wrap outline-none focus-visible:ring-2"
            >
              {row.tokens.map((t, i) => (
                <span
                  key={i}
                  data-testid="token"
                  className={cn(
                    "bg-muted/40 mr-px rounded-[2px] py-0.5",
                    (query === i || (hover?.[0] === r && hover[1] === i)) &&
                      "outline-foreground outline",
                    grid && "cursor-pointer",
                  )}
                  style={{ backgroundImage: shade(values(r)[i], max) }}
                  onMouseEnter={() => setHover([r, i])}
                  onClick={grid ? () => toggle(i) : undefined}
                  title={`${i} ${JSON.stringify(t)}: ${values(r)[i].toFixed(3)}`}
                >
                  {t.replaceAll("\n", "↵\n")}
                </span>
              ))}
            </p>
          </div>
        ))}
      </div>
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <Scale max={max} />
        <span className="text-foreground font-mono tabular-nums" aria-live="polite">
          {readout}
        </span>
      </div>
      {grid && (
        <HeatmapFigure
          key={series}
          view={{
            kind: "heatmap",
            title: series,
            z: grid,
            x: view.rows[0].tokens.map((t, i) => `${i}:${t}`),
            y: view.rows[0].tokens.map((t, i) => `${i}:${t}`),
            x_label: "key",
            y_label: "query",
          }}
        />
      )}
    </div>
  );
}

function TableFigure({ view }: { view: TableView }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {view.columns.map((c) => (
            <TableHead key={c}>{c}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {view.rows.map((row, i) => (
          <TableRow key={i}>
            {row.map((v, j) => {
              const href = view.links?.[i]?.[j];
              const text = v === null ? "—" : typeof v === "number" ? num(v) : String(v);
              return (
                <TableCell
                  key={j}
                  className={
                    typeof v === "number"
                      ? "text-right font-mono tabular-nums"
                      : "max-w-md align-top text-sm whitespace-pre-wrap"
                  }
                >
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      className="underline-offset-4 hover:underline"
                    >
                      {text}
                    </a>
                  ) : (
                    text
                  )}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
