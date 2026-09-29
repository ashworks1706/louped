"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import Link from "next/link";
import { parseAsInteger, parseAsString, useQueryStates } from "nuqs";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { QueryState } from "@/components/query-state";
import { Figure } from "@/components/run-views";
import { Button } from "@/components/ui/button";
import { q, type FeatureDashboard } from "@/lib/api";
import { num } from "@/lib/format";

/** One SAE feature's dashboard, as `loupe features` logged it: what it fires on and how often,
 * and what its decoder direction does to the next token. */
export function FeatureView() {
  const [s] = useQueryStates({ run: parseAsString, f: parseAsInteger });
  if (!s.run || s.f == null) {
    return <p className="text-muted-foreground p-6 text-sm">No feature selected.</p>;
  }
  return <Loaded run={s.run} feature={s.f} />;
}

function Loaded({ run, feature }: { run: string; feature: number }) {
  const dash = useQuery(q.feature(run, feature));
  const all = useQuery(q.features(run));
  const list = all.data ?? [];
  const at = list.indexOf(feature);
  const href = (f: number) => `/feature/?run=${encodeURIComponent(run)}&f=${f}`;
  return (
    <QueryState query={dash}>
      {(d) => (
        <>
          <header className="border-b">
            <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6">
              <Link
                href={`/run/?id=${encodeURIComponent(run)}&tab=figures`}
                className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
              >
                <ArrowLeft className="size-3" /> All features of this run
              </Link>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-semibold tracking-tight">Feature #{d.feature}</h1>
                <div className="ml-auto flex items-center gap-1">
                  <Step to={at > 0 ? href(list[at - 1]) : null} label="Previous feature">
                    <ChevronLeft />
                  </Step>
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {at >= 0 ? `${at + 1} of ${list.length}` : ""}
                  </span>
                  <Step
                    to={at >= 0 && at < list.length - 1 ? href(list[at + 1]) : null}
                    label="Next feature"
                  >
                    <ChevronRight />
                  </Step>
                </div>
              </div>
              <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
                <Stat label="Hook" value={d.hook} mono />
                {d.model && <Stat label="Model" value={d.model} mono />}
                {d.sae && (
                  <Stat label="SAE" value={d.sae_id ? `${d.sae} · ${d.sae_id}` : d.sae} mono />
                )}
                <Stat label="Density" value={`${(d.density * 100).toPrecision(3)}%`} mono />
                <Stat label="Max activation" value={num(d.max)} mono />
                {d.neuronpedia && (
                  <a
                    href={d.neuronpedia}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-foreground inline-flex items-center gap-1"
                  >
                    Neuronpedia <ExternalLink className="size-3" />
                  </a>
                )}
              </dl>
            </div>
          </header>
          <section className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-6">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)]">
              <Logits title="Promotes" rows={d.promoted} />
              <Logits title="Suppresses" rows={d.suppressed} />
              <Histogram dash={d} />
            </div>
            <Figure view={d.examples} />
          </section>
        </>
      )}
    </QueryState>
  );
}

function Step({
  to,
  label,
  children,
}: {
  to: string | null;
  label: string;
  children: React.ReactNode;
}) {
  if (!to) {
    return (
      <Button variant="ghost" size="sm" disabled aria-label={label}>
        {children}
      </Button>
    );
  }
  return (
    <Button variant="ghost" size="sm" asChild>
      <Link href={to} aria-label={label}>
        {children}
      </Link>
    </Button>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-1.5">
      <dt>{label}</dt>
      <dd className={mono ? "text-foreground font-mono text-xs leading-5" : "text-foreground"}>
        {value}
      </dd>
    </div>
  );
}

/** The next tokens the feature's decoder direction pushes up or down through the unembedding. */
function Logits({ title, rows }: { title: string; rows: FeatureDashboard["promoted"] }) {
  const tone = title === "Promotes" ? "text-positive" : "text-negative";
  return (
    <figure className="rounded-xl border">
      <figcaption className="border-b px-4 py-3 text-sm font-medium">{title}</figcaption>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([token, value], i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="px-4 py-1.5 font-mono text-xs whitespace-pre">
                {JSON.stringify(token).slice(1, -1)}
              </td>
              <td className={`px-4 py-1.5 text-right font-mono text-xs tabular-nums ${tone}`}>
                {value > 0 ? "+" : ""}
                {value.toFixed(3)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function Histogram({ dash }: { dash: FeatureDashboard }) {
  const { edges, counts } = dash.histogram;
  const data = counts.map((count, i) => ({ at: (edges[i] + edges[i + 1]) / 2, count }));
  return (
    <figure className="rounded-xl border">
      <figcaption className="flex items-baseline justify-between border-b px-4 py-3">
        <span className="text-sm font-medium">Activations when it fires</span>
        <span className="text-muted-foreground text-xs">tokens by activation</span>
      </figcaption>
      <div className="h-56 p-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="at"
              tickFormatter={(v: number) => v.toFixed(1)}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <Tooltip
              cursor={{ fill: "var(--muted)" }}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelFormatter={(v) => `activation ≈ ${Number(v).toFixed(2)}`}
            />
            <Bar dataKey="count" fill="var(--foreground)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
