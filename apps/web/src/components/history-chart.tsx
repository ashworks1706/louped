"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { part, partId } from "@/components/parts";
import type { RunDetail } from "@/lib/api";
import { AXIS_TICK, TOOLTIP_STYLE } from "@/lib/chart";
import { isSystem } from "@/lib/format";

const short = new Intl.NumberFormat("en", { notation: "compact", maximumSignificantDigits: 3 });

/** Axis ticks that fit in 48px: 0.0045 stays readable, 78240 becomes 78.2K. */
export function compact(v: number): string {
  if (v === 0) return "0";
  return Math.abs(v) < 0.01 ? v.toExponential(0) : short.format(v);
}

/** One small chart per metric logged over steps. Metrics with a single point are not charted.
 * With against, two runs' curves overlay on each metric both logged: the baseline (A) thin and
 * muted, the changed run (B) in full. */
export function HistoryCharts({
  history,
  against,
}: {
  history: RunDetail["history"];
  against?: RunDetail["history"];
}) {
  const curve = (h: RunDetail["history"], k: string) => (h[k]?.length ?? 0) > 1 && !isSystem(k);
  const names = Object.keys(history).filter(
    (k) => curve(history, k) && (!against || curve(against, k)),
  );
  if (names.length === 0) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {names.map((name) => {
        const steps = new Map<number, { step: number; value?: number; base?: number }>();
        for (const p of history[name]) steps.set(p.step, { step: p.step, value: p.value });
        for (const p of against?.[name] ?? [])
          steps.set(p.step, { ...(steps.get(p.step) ?? { step: p.step }), base: p.value });
        const data = [...steps.values()].sort((a, b) => a.step - b.step);
        return (
          <div
            key={name}
            className="rounded-xl border p-4"
            {...part(partId("curves/metric", name))}
          >
            <div className="mb-3 flex items-center gap-3 text-sm font-medium">
              {name}
              {against && (
                <span className="text-muted-foreground font-mono text-xs font-normal">
                  A dashed · B solid
                </span>
              )}
            </div>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="step" tick={AXIS_TICK} tickLine={false} axisLine={false} />
                  <YAxis
                    tick={AXIS_TICK}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    tickFormatter={compact}
                  />
                  <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(s) => `step ${s}`} />
                  {against && (
                    <Line
                      type="monotone"
                      dataKey="base"
                      name="A"
                      stroke="var(--muted-foreground)"
                      strokeDasharray="4 3"
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                  <Line
                    type="monotone"
                    dataKey="value"
                    name={against ? "B" : name}
                    stroke="var(--foreground)"
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      })}
    </div>
  );
}
