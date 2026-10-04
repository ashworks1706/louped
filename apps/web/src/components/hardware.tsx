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

import { Help } from "@/components/help";
import { compact } from "@/components/history-chart";
import { Stat, StatGrid } from "@/components/stat-grid";
import type { RunDetail } from "@/lib/api";
import { AXIS_TICK, TOOLTIP_STYLE } from "@/lib/chart";

type History = RunDetail["history"];
type Point = { t: number; v: number };

const GPU = /^system\/gpu_(\d+)_(power_usage_watts|utilization_percentage|memory_usage_megabytes)$/;

/** Each sampled series as (seconds since the run's first sample, value). */
function timed(history: History): Map<string, Point[]> {
  const system = Object.entries(history).filter(
    ([k, pts]) => k.startsWith("system/") && pts.some((p) => p.timestamp != null),
  );
  const t0 = Math.min(
    ...system.flatMap(([, pts]) => pts.map((p) => p.timestamp ?? Number.POSITIVE_INFINITY)),
  );
  return new Map(
    system.map(([k, pts]) => [
      k,
      pts
        .filter((p) => p.timestamp != null)
        .map((p) => ({ t: ((p.timestamp ?? t0) - t0) / 1000, v: p.value }))
        .sort((a, b) => a.t - b.t),
    ]),
  );
}

/** Joules: power in watts integrated over seconds (trapezoids between samples). */
function joules(points: Point[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    total += ((points[i].v + points[i - 1].v) / 2) * (points[i].t - points[i - 1].t);
  }
  return total;
}

const peak = (pts: Point[] | undefined) => (pts?.length ? Math.max(...pts.map((p) => p.v)) : null);
const mean = (pts: Point[] | undefined) =>
  pts?.length ? pts.reduce((a, p) => a + p.v, 0) / pts.length : null;

function energy(j: number): string {
  return j >= 3600 ? `${(j / 3600).toFixed(2)} Wh` : `${j.toFixed(0)} J`;
}

/** Whether a run carries samples of the machine it ran on. */
export function hasHardware(history: History): boolean {
  return Object.keys(history).some((k) => k.startsWith("system/") && history[k].length > 1);
}

/** The machine while the run was open: GPU energy, power, utilisation and memory per GPU, and
 * CPU and RAM, sampled by MLflow every few seconds. NVML sees every process on a GPU, so a model
 * served by another process on the same machine is counted too. */
export function Hardware({ history }: { history: History }) {
  const series = timed(history);
  const gpus = [...new Set([...series.keys()].map((k) => GPU.exec(k)?.[1]).filter(Boolean))];
  const power = gpus.map((g) => series.get(`system/gpu_${g}_power_usage_watts`) ?? []);
  const total = power.reduce((a, pts) => a + joules(pts), 0);
  const seconds = Math.max(0, ...[...series.values()].map((pts) => pts.at(-1)?.t ?? 0));
  const charts: [string, string, Point[] | undefined][] = [
    ...gpus.flatMap((g): [string, string, Point[] | undefined][] => [
      [`GPU ${g} power`, "W", series.get(`system/gpu_${g}_power_usage_watts`)],
      [`GPU ${g} utilisation`, "%", series.get(`system/gpu_${g}_utilization_percentage`)],
      [`GPU ${g} memory`, "MB", series.get(`system/gpu_${g}_memory_usage_megabytes`)],
    ]),
    ["CPU", "%", series.get("system/cpu_utilization_percentage")],
    ["RAM", "MB", series.get("system/system_memory_usage_megabytes")],
  ];
  const gpuMem = Math.max(
    0,
    ...gpus.map((g) => peak(series.get(`system/gpu_${g}_memory_usage_megabytes`)) ?? 0),
  );
  const ram = peak(series.get("system/system_memory_usage_megabytes"));
  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-center gap-1.5 text-sm font-medium">
        Hardware
        <Help>
          The machine while the run was open, sampled every few seconds: GPU power, utilisation and
          memory (NVML), CPU and RAM. NVML counts every process on a GPU, including a model served
          by another process; the CPU and RAM are the whole machine&apos;s.
        </Help>
      </h2>
      <StatGrid>
        {gpus.length > 0 && (
          <>
            <Stat label="GPU energy" note={`over ${seconds.toFixed(0)} s, all GPUs`}>
              {energy(total)}
            </Stat>
            <Stat label="GPU power, peak" note={`mean ${(mean(power.flat()) ?? 0).toFixed(0)} W`}>
              {`${Math.max(0, ...power.map((p) => peak(p) ?? 0)).toFixed(0)} W`}
            </Stat>
            <Stat label="GPU memory, peak">{`${(gpuMem / 1024).toFixed(1)} GB`}</Stat>
          </>
        )}
        {ram != null && <Stat label="RAM, peak">{`${(ram / 1024).toFixed(1)} GB`}</Stat>}
      </StatGrid>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {charts
          .filter(([, , pts]) => (pts?.length ?? 0) > 1)
          .map(([title, unit, pts]) => (
            <div key={title} className="rounded-xl border p-4">
              <div className="mb-3 text-sm font-medium">
                {title} <span className="text-muted-foreground font-normal">({unit})</span>
              </div>
              <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pts} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                    <CartesianGrid stroke="var(--border)" vertical={false} />
                    <XAxis
                      dataKey="t"
                      type="number"
                      domain={["dataMin", "dataMax"]}
                      tick={AXIS_TICK}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(s: number) => `${s.toFixed(0)}s`}
                    />
                    <YAxis
                      tick={AXIS_TICK}
                      tickLine={false}
                      axisLine={false}
                      width={48}
                      tickFormatter={compact}
                    />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      labelFormatter={(s) => `${Number(s).toFixed(0)} s`}
                      formatter={(v) => [`${Number(v).toFixed(1)} ${unit}`, title]}
                    />
                    <Line
                      type="monotone"
                      dataKey="v"
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
    </section>
  );
}
