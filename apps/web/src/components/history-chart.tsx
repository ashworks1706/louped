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

import type { RunDetail } from "@/lib/api";
import { AXIS_TICK, TOOLTIP_STYLE } from "@/lib/chart";

const short = new Intl.NumberFormat("en", { notation: "compact", maximumSignificantDigits: 3 });

/** Axis ticks that fit in 48px: 0.0045 stays readable, 78240 becomes 78.2K. */
function compact(v: number): string {
  if (v === 0) return "0";
  return Math.abs(v) < 0.01 ? v.toExponential(0) : short.format(v);
}

/** One small chart per metric logged over steps. Metrics with a single point are not charted. */
export function HistoryCharts({ history }: { history: RunDetail["history"] }) {
  const series = Object.entries(history).filter(([, pts]) => pts.length > 1);
  if (series.length === 0) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {series.map(([name, points]) => (
        <div key={name} className="rounded-xl border p-4">
          <div className="mb-3 text-sm font-medium">{name}</div>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
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
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="var(--foreground)"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
    </div>
  );
}
