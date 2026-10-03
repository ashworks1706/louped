"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricName } from "@/components/term";
import { ArrowLeft, ListTree } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { HistoryCharts } from "@/components/history-chart";
import { MetricValue } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { KindBadge, StatusDot } from "@/components/run-badges";
import { RunViews } from "@/components/run-views";
import { StatGrid } from "@/components/stat-grid";
import { SamplesTable } from "@/components/samples-table";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { API, isLive, q, type RunDetail } from "@/lib/api";
import { ago, headline } from "@/lib/format";
import { experimentHref } from "@/lib/href";

export function RunView() {
  const [id] = useQueryState("id", parseAsString);
  if (!id) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={ListTree}
          title="No run selected"
          body="Open one from Runs."
          action={{ href: "/runs/", label: "Open Runs" }}
        />
      </section>
    );
  }
  return <RunLoaded id={id} />;
}

function RunLoaded({ id }: { id: string }) {
  const run = useQuery(q.run(id));
  if (!run.data) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <QueryState query={run}>{() => null}</QueryState>
      </section>
    );
  }
  return (
    <>
      <RunHeader run={run.data} />
      <section className="mx-auto max-w-6xl px-6 py-6">
        <RunTabs run={run.data} />
      </section>
    </>
  );
}

function RunHeader({ run }: { run: RunDetail }) {
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6">
        <Link
          href="/runs/"
          className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
        >
          <ArrowLeft className="size-3" /> Runs
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{run.name}</h1>
          <KindBadge kind={run.kind} />
          <StatusDot status={run.status} samples={run.samples} total={run.total} />
        </div>
        <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt>Model</dt>
            <dd className="text-foreground font-mono">{run.model ?? "—"}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Experiment</dt>
            <dd className="text-foreground">
              {run.experiment ? (
                <Link href={experimentHref(run.experiment)} className="hover:underline">
                  {run.experiment}
                </Link>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Created</dt>
            <dd className="text-foreground">{ago(run.created)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Id</dt>
            <dd className="text-foreground font-mono text-xs leading-5">{run.id}</dd>
          </div>
        </dl>
      </div>
    </header>
  );
}

function RunTabs({ run }: { run: RunDetail }) {
  const [chosen, setTab] = useQueryState("tab", parseAsString);
  // Samples and figures poll only while the run is live; read them once more when it ends.
  const client = useQueryClient();
  const wasLive = useRef(isLive(run.status));
  useEffect(() => {
    if (wasLive.current && !isLive(run.status)) {
      void client.invalidateQueries({ queryKey: ["samples", run.id] });
      void client.invalidateQueries({ queryKey: ["views", run.id] });
    }
    wasLive.current = isLive(run.status);
  }, [client, run.id, run.status]);
  const isEval = run.kind === "eval";
  const hasFigures = run.artifacts.some((a) => a.path.startsWith("views/"));
  // A run whose results are only figures opens on them.
  const tab = chosen ?? (hasFigures && headline(run.metrics).length === 0 ? "figures" : "overview");
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        {hasFigures && <TabsTrigger value="figures">Figures</TabsTrigger>}
        {isEval && <TabsTrigger value="samples">Samples</TabsTrigger>}
        {run.log && <TabsTrigger value="log">Log</TabsTrigger>}
        {!isEval && <TabsTrigger value="artifacts">Artifacts</TabsTrigger>}
        <TabsTrigger value="config">Config</TabsTrigger>
      </TabsList>
      <TabsContent value="overview">
        <Overview run={run} />
      </TabsContent>
      {hasFigures && (
        <TabsContent value="figures">
          <RunViews id={run.id} live={isLive(run.status)} />
        </TabsContent>
      )}
      {isEval && (
        <TabsContent value="samples">
          <Samples id={run.id} hasLog={!!run.log} live={isLive(run.status)} />
        </TabsContent>
      )}
      {run.log && (
        <TabsContent value="log">
          <InspectFrame log={run.log} />
        </TabsContent>
      )}
      {!isEval && (
        <TabsContent value="artifacts">
          <Artifacts run={run} />
        </TabsContent>
      )}
      <TabsContent value="config">
        <KeyValues title="Parameters" values={run.params} />
        <div className="h-6" />
        <KeyValues title="Tags" values={run.tags} />
      </TabsContent>
    </Tabs>
  );
}

function Overview({ run }: { run: RunDetail }) {
  const metrics = headline(run.metrics);
  return (
    <div className="flex flex-col gap-6">
      {run.error && (
        <pre className="border-negative/30 bg-negative/5 text-negative overflow-x-auto rounded-xl border p-4 text-xs whitespace-pre-wrap">
          {run.error}
        </pre>
      )}
      {metrics.length > 0 ? (
        <StatGrid>
          {metrics.map(([key, value, err]) => (
            <div key={key} className="flex flex-col gap-1 p-4">
              <MetricName k={key} className="text-muted-foreground text-xs" />
              <MetricValue value={value} err={err} className="text-2xl font-medium" />
            </div>
          ))}
        </StatGrid>
      ) : (
        <p className="text-muted-foreground text-sm">
          No metrics recorded.
          {run.artifacts.some((a) => a.path.startsWith("views/")) &&
            " Its results are figures, under Figures."}
        </p>
      )}
      <HistoryCharts history={run.history} />
    </div>
  );
}

/** Inspect View, served by loupe at /inspect, open at this run's log or at the selected sample.
 * Its theme is the one resolved on first render, so toggling the theme does not reload it. */
function InspectFrame({ log }: { log: string }) {
  const [sample] = useQueryState("sample", parseAsString);
  const [epoch] = useQueryState("epoch", parseAsInteger);
  const { resolvedTheme } = useTheme();
  const [theme, setTheme] = useState(resolvedTheme);
  if (theme === undefined && resolvedTheme !== undefined) setTheme(resolvedTheme);
  const height = "h-[calc(100svh-16rem)] min-h-96 w-full rounded-xl";
  if (!theme) return <Skeleton className={height} />;
  const at = sample ? `sample/${encodeURIComponent(sample)}/${epoch ?? 1}/` : "";
  return (
    <iframe
      title="Inspect View"
      src={`${API}/inspect/?inspectLogviewThemeCategory=${theme}#/logs/${log}/samples/${at}`}
      className={`${height} border`}
    />
  );
}

function Samples({ id, hasLog, live }: { id: string; hasLog: boolean; live: boolean }) {
  const samples = useQuery(q.samples(id, live));
  return (
    <QueryState query={samples} rows={8}>
      {(s) => <SamplesTable runId={id} samples={s} hasLog={hasLog} />}
    </QueryState>
  );
}

function Artifacts({ run }: { run: RunDetail }) {
  if (run.artifacts.length === 0) {
    return <p className="text-muted-foreground text-sm">No artifacts.</p>;
  }
  return (
    <ul className="divide-y rounded-xl border">
      {run.artifacts.map((a) => (
        <li key={a.path} className="flex items-center justify-between px-4 py-2.5 text-sm">
          <a
            className="font-mono hover:underline"
            href={`${API}/api/runs/${encodeURIComponent(run.id)}/artifacts/${a.path}`}
            target="_blank"
            rel="noreferrer"
          >
            {a.path}
          </a>
          <span className="text-muted-foreground font-mono text-xs">
            {a.size != null ? `${(a.size / 1024).toFixed(1)} KB` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function KeyValues({ title, values }: { title: string; values: Record<string, string> }) {
  const entries = Object.entries(values);
  return (
    <div>
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      {entries.length === 0 ? (
        <p className="text-muted-foreground text-sm">None.</p>
      ) : (
        <dl className="divide-y rounded-xl border">
          {entries.map(([k, v]) => (
            <div
              key={k}
              className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-4 px-4 py-2 text-sm"
            >
              <dt className="text-muted-foreground truncate font-mono">{k}</dt>
              <dd className="font-mono break-all">{v || "—"}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
