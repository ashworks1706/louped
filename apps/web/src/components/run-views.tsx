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
import { q, type HeatmapView, type LineView, type RunView, type TableView } from "@/lib/api";
import { num } from "@/lib/format";

/** Every figure a run logged under views/, in file order. */
export function RunViews({ id }: { id: string }) {
  const views = useQuery(q.views(id));
  return (
    <QueryState query={views}>
      {(all) => (
        <div className="flex flex-col gap-6">
          {all.map((v) => (
            <ViewCard key={v.path} item={v} />
          ))}
        </div>
      )}
    </QueryState>
  );
}

function ViewCard({ item }: { item: RunView }) {
  const { view } = item;
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

/** Signed values: positive shades one way, negative the other, strength by magnitude. With
 * slices (attention: one per layer and head), a select picks which grid is drawn. */
function HeatmapFigure({ view }: { view: HeatmapView }) {
  const [hover, setHover] = useState<[number, number] | null>(null);
  const names = Object.keys(view.slices ?? {});
  const [slice, setSlice] = useState(names[0]);
  const z = view.slices?.[slice] ?? view.z;
  const max = Math.max(1e-9, ...z.flat().map(Math.abs));
  const cell = (v: number) =>
    `color-mix(in oklch, var(${v >= 0 ? "--positive" : "--negative"}) ${Math.round(
      (Math.abs(v) / max) * 100,
    )}%, transparent)`;
  const shown = hover ? z[hover[0]][hover[1]] : null;
  return (
    <div className="flex flex-col gap-3">
      {names.length > 0 && (
        <NativeSelect
          aria-label="Slice"
          value={slice}
          onChange={(e) => setSlice(e.target.value)}
          className="font-mono text-xs"
        >
          {names.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </NativeSelect>
      )}
      <div className="overflow-x-auto">
        <div
          className="grid w-max gap-px text-[10px]"
          style={{ gridTemplateColumns: `auto repeat(${view.x.length}, minmax(28px, 1fr))` }}
          onMouseLeave={() => setHover(null)}
        >
          {view.y.map((y, r) => (
            <Fragment key={y}>
              <span className="text-muted-foreground pr-2 text-right font-mono leading-6">{y}</span>
              {view.x.map((x, c) => (
                <span
                  key={x}
                  data-testid="heat-cell"
                  className="bg-muted h-6 rounded-[2px] outline-offset-1 hover:outline hover:outline-1"
                  style={{
                    backgroundImage: `linear-gradient(${cell(z[r][c])}, ${cell(z[r][c])})`,
                  }}
                  onMouseEnter={() => setHover([r, c])}
                  title={`${view.y_label} ${y} · ${view.x_label} ${x}: ${z[r][c].toFixed(3)}`}
                />
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
        <span className="flex items-center gap-1.5">
          <span className="font-mono">−{max.toFixed(2)}</span>
          <span
            className="h-2 w-24 rounded-full"
            style={{
              background:
                "linear-gradient(to right, var(--negative), transparent, var(--positive))",
            }}
          />
          <span className="font-mono">+{max.toFixed(2)}</span>
        </span>
        <span className="text-foreground font-mono tabular-nums" aria-live="polite">
          {hover && shown !== null
            ? `${view.y_label} ${view.y[hover[0]]}, ${view.x[hover[1]]}: ${shown.toFixed(3)}`
            : " "}
        </span>
      </div>
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
