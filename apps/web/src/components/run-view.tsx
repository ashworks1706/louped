"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricName } from "@/components/term";
import { ArrowLeft, ListTree } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";

import { ArtifactBrowser, RunFile } from "@/components/artifact-browser";
import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { hasItems, ItemsView } from "@/components/items-view";
import { EditableText } from "@/components/markdown-editor";
import { Hardware, hasHardware } from "@/components/hardware";
import { HistoryCharts } from "@/components/history-chart";
import { MetricValue } from "@/components/metric";
import { QueryState } from "@/components/query-state";
import { HostBadge, KindBadge, StatusDot } from "@/components/run-badges";
import { Figure, RunViews } from "@/components/run-views";
import { StatGrid } from "@/components/stat-grid";
import { SamplesTable } from "@/components/samples-table";
import { Skeleton } from "@/components/ui/skeleton";
import { DeleteButton } from "@/components/delete-button";
import { PluginFrame } from "@/components/plugin-page";
import {
  blockId,
  LayoutErrors,
  PluginBlock,
  RegionGrid,
  textBlock,
  useLayout,
} from "@/components/layout";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  API,
  deleteRun,
  isLive,
  q,
  saveArtifact,
  type Block,
  type PluginInfo,
  type RunDetail,
} from "@/lib/api";
import { artifactQuery } from "@/lib/artifacts";
import { cn } from "@/lib/utils";
import { ago, headline, metricLabel } from "@/lib/format";
import { ExperimentLink } from "@/components/experiment-link";
import { Help } from "@/components/help";
import { arrange, part, partId, PartNote, PartScope, useRules } from "@/components/parts";

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
    <PartScope experiment={run.data.experiment}>
      <RunHeader run={run.data} />
      <section className="mx-auto max-w-6xl px-6 py-6">
        <RunTabs run={run.data} />
      </section>
    </PartScope>
  );
}

function RunHeader({ run }: { run: RunDetail }) {
  const rule = useRules();
  const meta: { name: string; label: string; value: React.ReactNode; className?: string }[] = [
    { name: "model", label: "Model", value: run.model ?? "—", className: "font-mono" },
    {
      name: "experiment",
      label: "Experiment",
      value: run.experiment ? <ExperimentLink name={run.experiment} /> : "—",
    },
    { name: "created", label: "Created", value: ago(run.created) },
    { name: "id", label: "Id", value: run.id, className: "font-mono text-xs leading-5" },
  ];
  const badge = (name: string, el: React.ReactNode) =>
    rule(partId("run/badge", name)).hidden ? null : (
      <span {...part(partId("run/badge", name))} className="inline-flex">
        {el}
      </span>
    );
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6">
        <Link
          href="/runs/"
          className={cn(
            "text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs",
            rule("run/back").hidden && "hidden",
          )}
          {...part("run/back")}
        >
          <ArrowLeft className="size-3" /> Runs
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight" {...part("run/title")}>
            {run.name}
          </h1>
          {badge("kind", <KindBadge kind={run.kind} />)}
          {badge("host", <HostBadge host={run.host} />)}
          {badge(
            "status",
            <StatusDot status={run.status} samples={run.samples} total={run.total} />,
          )}
          {!rule("run/delete").hidden && (
            <div className="ml-auto" {...part("run/delete")}>
              <DeleteButton
                what="run"
                name={run.name}
                undo={
                  run.id.startsWith("e-")
                    ? "Its eval log moves to .louped/trash/logs; move it back to restore the run."
                    : "MLflow keeps it marked deleted until mlflow gc; MlflowClient.restore_run brings it back."
                }
                remove={() => deleteRun(run.id)}
                then="/runs/"
                disabled={isLive(run.status) ? "Still running: cancel its job first" : undefined}
              />
            </div>
          )}
        </div>
        <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {arrange(meta, (m) => partId("run/meta", m.name), rule).map((m) => {
            const r = rule(partId("run/meta", m.name));
            return (
              <div key={m.name} className="flex gap-1.5" {...part(partId("run/meta", m.name))}>
                <dt className="flex items-center gap-1">
                  {r.label ?? m.label}
                  {r.about && <Help>{r.about}</Help>}
                </dt>
                <dd className={cn("text-foreground", m.className)}>{m.value}</dd>
              </div>
            );
          })}
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
  const layout = useLayout(run.experiment);
  const plugins = useQuery(q.plugins());
  if (!layout.data) return <QueryState query={layout}>{() => null}</QueryState>;
  const hasFigures = run.artifacts.some((a) => a.path.startsWith("views/"));
  const tabs = layout.data.regions["run.tabs"].flatMap((b, at) => {
    const t =
      b.block === "text"
        ? { value: `t-${at}`, label: "Notes", ...textBlock(b) }
        : runTab(run, b, layout.data.regions["run.overview"], plugins.data ?? []);
    return t ? [{ ...t, b, at, label: b.title ?? t.label }] : [];
  });
  const values = tabs.map((t) => t.value);
  // A run whose results are only figures opens on them.
  const first =
    values[0] === "overview" &&
    hasFigures &&
    headline(run.metrics).length === 0 &&
    values.includes("figures")
      ? "figures"
      : values[0];
  const tab = chosen && values.includes(chosen) ? chosen : first;
  return (
    <>
      <LayoutErrors page={layout.data} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger key={t.value} value={t.value} data-part={blockId("run.tabs", t.b, t.at)}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.value} value={t.value}>
            {t.body}
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}

/** A run.tabs block as a tab: its value in ?tab=, its name and what it holds; null when this run
 * has nothing for it (Samples on a run that is not an eval). */
function runTab(
  run: RunDetail,
  b: Block,
  overview: Block[],
  plugins: PluginInfo[],
): { value: string; label: string; body: React.ReactNode } | null {
  const live = isLive(run.status);
  switch (b.block) {
    case "overview":
      return {
        value: "overview",
        label: "Overview",
        body: <Overview run={run} blocks={overview} />,
      };
    case "items":
      return hasItems(run)
        ? { value: "items", label: "Items", body: <ItemsView run={run} /> }
        : null;
    case "figures":
      return run.artifacts.some((a) => a.path.startsWith("views/"))
        ? { value: "figures", label: "Figures", body: <RunViews id={run.id} live={live} /> }
        : null;
    case "samples":
      return run.kind === "eval"
        ? {
            value: "samples",
            label: "Samples",
            body: <Samples id={run.id} hasLog={!!run.log} live={live} />,
          }
        : null;
    case "log":
      return run.log ? { value: "log", label: "Log", body: <InspectFrame log={run.log} /> } : null;
    case "artifacts":
      return run.artifacts.some((a) => !a.path.startsWith("views/"))
        ? { value: "artifacts", label: "Artifacts", body: <ArtifactBrowser run={run} /> }
        : null;
    case "config":
      return {
        value: "config",
        label: "Config",
        body: (
          <>
            <KeyValues title="Parameters" values={run.params} kind="config/param" />
            <div className="h-6" />
            <KeyValues title="Tags" values={run.tags} kind="config/tag" />
          </>
        ),
      };
    case "file":
      return run.artifacts.some((a) => a.path === b.path)
        ? { value: `f-${b.path}`, label: b.path!, body: <RunFile run={run} path={b.path!} /> }
        : null;
    case "plugin":
      return {
        value: `x-${b.plugin}`,
        label: plugins.find((p) => p.name === b.plugin)?.title ?? b.plugin!,
        body: (
          <PluginFrame
            name={b.plugin!}
            page={b.page ?? "run.html"}
            query={{ run: run.id, ...(run.experiment ? { experiment: run.experiment } : {}) }}
          />
        ),
      };
    default:
      return null;
  }
}

/** The metrics block: a card per headline metric, each a part the layout can rename, explain,
 * reorder or hide. */
function Metrics({ metrics }: { metrics: ReturnType<typeof headline> }) {
  const rule = useRules();
  const id = (key: string) => partId("run.overview/metrics", key);
  return (
    <StatGrid>
      {arrange(metrics, ([key]) => id(key), rule).map(([key, value, err]) => {
        const r = rule(id(key));
        return (
          <div key={key} {...part(id(key))} className="flex flex-col gap-1 p-4">
            {r.label || r.about ? (
              <span className="text-muted-foreground flex items-center gap-1 text-xs">
                {r.label ?? metricLabel(key)}
                {r.about && <Help>{r.about}</Help>}
              </span>
            ) : (
              <MetricName k={key} className="text-muted-foreground text-xs" />
            )}
            <MetricValue value={value} err={err} className="text-2xl font-medium" />
            <PartNote rule={r} />
          </div>
        );
      })}
    </StatGrid>
  );
}

/** The run.overview region: its blocks, each drawn when this run has something for it. */
function Overview({ run, blocks }: { run: RunDetail; blocks: Block[] }) {
  return <RegionGrid region="run.overview" blocks={blocks} render={(b) => overviewBlock(run, b)} />;
}

function overviewBlock(
  run: RunDetail,
  b: Block,
): { title?: string; about?: string; body: React.ReactNode } | null {
  const has = (path: string) => run.artifacts.some((a) => a.path === path);
  const metrics = headline(run.metrics);
  switch (b.block) {
    case "error":
      return run.error
        ? {
            body: (
              <pre className="border-negative/30 bg-negative/5 text-negative overflow-x-auto rounded-xl border p-4 text-xs whitespace-pre-wrap">
                {run.error}
              </pre>
            ),
          }
        : null;
    case "metrics":
      return {
        body:
          metrics.length > 0 ? (
            <Metrics metrics={metrics} />
          ) : (
            <p className="text-muted-foreground text-sm">
              No metrics recorded.
              {run.artifacts.some((a) => a.path.startsWith("views/")) &&
                " Its results are figures, under Figures."}
            </p>
          ),
      };
    case "metric": {
      const found = metrics.find(([key]) => key === b.key);
      return {
        body: (
          <StatGrid className="sm:grid-cols-1 lg:grid-cols-1">
            <div className="flex flex-col gap-1 p-4">
              <MetricName k={b.key!} className="text-muted-foreground text-xs" />
              {found ? (
                <MetricValue value={found[1]} err={found[2]} className="text-2xl font-medium" />
              ) : (
                <span className="text-muted-foreground text-sm">Not recorded by this run.</span>
              )}
            </div>
          </StatGrid>
        ),
      };
    }
    case "history":
      return { body: <HistoryCharts history={run.history} /> };
    case "hardware":
      return hasHardware(run.history) ? { body: <Hardware history={run.history} /> } : null;
    case "report":
      return has("report.md") ? { title: "Report", body: <Report runId={run.id} /> } : null;
    case "file":
      return {
        title: b.path!,
        body: has(b.path!) ? (
          <RunFile run={run} path={b.path!} />
        ) : (
          <p className="text-muted-foreground text-sm">This run wrote no {b.path}.</p>
        ),
      };
    case "figure":
      return { body: <RunFigure id={run.id} index={b.index!} b={b} live={isLive(run.status)} /> };
    case "provenance":
      return { title: "Provenance", body: <Provenance run={run} /> };
    case "plugin":
      return {
        body: (
          <PluginBlock
            b={b}
            page="run.html"
            query={{ run: run.id, ...(run.experiment ? { experiment: run.experiment } : {}) }}
          />
        ),
      };
    default:
      return null;
  }
}

/** One of the run's figures, by index; the block's title and about over the figure's own. */
function RunFigure({ id, index, b, live }: { id: string; index: number; b: Block; live: boolean }) {
  const views = useQuery(q.views(id, live));
  return (
    <QueryState query={views}>
      {(all) =>
        all[index] ? (
          <Figure
            view={{
              ...all[index].view,
              title: b.title ?? all[index].view.title,
              about: b.about ?? all[index].view.about,
            }}
          />
        ) : (
          <p className="text-muted-foreground text-sm">
            This run has {all.length} figures; there is none at {index}.
          </p>
        )
      }
    </QueryState>
  );
}

/** The report a run wrote for people (report.md at its top level), rendered. */
function Report({ runId }: { runId: string }) {
  const text = useQuery(artifactQuery(runId, "report.md"));
  const client = useQueryClient();
  return (
    <QueryState query={text}>
      {(md) => (
        <article className="rounded-xl border px-6 py-5">
          <EditableText
            name="report.md"
            shown={md}
            save={async (t) => {
              await saveArtifact(runId, "report.md", t);
              await client.invalidateQueries({ queryKey: ["artifact", runId, "report.md"] });
            }}
          />
        </article>
      )}
    </QueryState>
  );
}

type Meta = {
  started_at?: string;
  python?: string;
  platform?: string;
  seed?: number | null;
  git?: { sha?: string | null; dirty?: boolean };
  packages?: Record<string, string>;
};

/** Where and how the run was made: the machine, the code and the environment, from its tags and
 * the RunMeta (meta.json) it wrote next to its results. */
function Provenance({ run }: { run: RunDetail }) {
  const rule = useRules();
  const hasMeta = run.artifacts.some((a) => a.path === "meta.json");
  const hasCommand = run.artifacts.some((a) => a.path === "command.txt");
  const meta = useQuery({ ...artifactQuery(run.id, "meta.json"), enabled: hasMeta });
  const command = useQuery({ ...artifactQuery(run.id, "command.txt"), enabled: hasCommand });
  let m: Meta = {};
  try {
    m = meta.data ? (JSON.parse(meta.data) as Meta) : {};
  } catch {
    m = {};
  }
  const sha = run.tags["louped.git_sha"] || m.git?.sha || "";
  const dirty = (run.tags["louped.git_dirty"] ?? String(m.git?.dirty ?? "")) === "true";
  const rows: [string, React.ReactNode][] = [
    [
      "Ran on",
      [run.host ?? "this machine", run.tags["louped.node"], run.tags["louped.gpu"]]
        .filter(Boolean)
        .join(" · "),
    ],
    [
      "Code",
      sha ? `${sha.slice(0, 12)}${dirty ? " (uncommitted changes)" : ""}` : "not a git checkout",
    ],
  ];
  // files changed in the app after the run wrote them: its results are no longer only its own
  if (run.tags["louped.edited"])
    rows.push(["Edited after", run.tags["louped.edited"].split(",").join(" · ")]);
  if (m.started_at) rows.push(["Started", m.started_at]);
  if (m.python) rows.push(["Python", m.python]);
  if (m.platform) rows.push(["Platform", m.platform]);
  if (m.seed !== undefined) rows.push(["Seed", String(m.seed ?? "none")]);
  if (m.packages && Object.keys(m.packages).length)
    rows.push([
      "Packages",
      Object.entries(m.packages)
        .map(([k, v]) => `${k} ${v}`)
        .join(" · "),
    ]);
  if (command.data)
    rows.push([
      "Command",
      <span key="command" className="flex min-w-0 items-start gap-2">
        <code className="bg-muted/50 min-w-0 flex-1 rounded-md p-2 font-mono text-xs break-all whitespace-pre-wrap">
          {command.data.trim()}
        </code>
        <CopyButton text={command.data.trim()} />
      </span>,
    ]);
  const id = (k: string) => partId("run.overview/provenance", k.toLowerCase().replace(/ /g, "-"));
  return (
    <dl className="divide-y rounded-xl border">
      {arrange(rows, ([k]) => id(k), rule).map(([k, v]) => {
        const r = rule(id(k));
        return (
          <div
            key={k}
            {...part(id(k))}
            className="grid grid-cols-[8rem_minmax(0,1fr)] gap-4 px-4 py-2 text-sm"
          >
            <dt className="text-muted-foreground flex items-start gap-1">
              {r.label ?? k}
              {r.about && <Help>{r.about}</Help>}
            </dt>
            <dd className="min-w-0 font-mono text-xs leading-5 break-words">{v}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/** Inspect View, served by louped at /inspect, open at this run's log or at the selected sample.
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

function KeyValues({
  title,
  values,
  kind,
}: {
  title: string;
  values: Record<string, string>;
  kind: "config/param" | "config/tag";
}) {
  const rule = useRules();
  const entries = arrange(Object.entries(values), ([k]) => partId(kind, k), rule);
  return (
    <div>
      <h2 className="mb-2 text-sm font-medium" {...part(`${kind}s`)}>
        {title}
      </h2>
      {entries.length === 0 ? (
        <p className="text-muted-foreground text-sm">None.</p>
      ) : (
        <dl className="divide-y rounded-xl border">
          {entries.map(([k, v]) => {
            const about = rule(partId(kind, k)).about;
            return (
              <div
                key={k}
                {...part(partId(kind, k))}
                className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-4 px-4 py-2 text-sm"
              >
                <dt className="text-muted-foreground flex min-w-0 items-center gap-1 font-mono">
                  <span className="truncate">{k}</span>
                  {about && <Help>{about}</Help>}
                </dt>
                <dd className="font-mono break-all">{v || "—"}</dd>
              </div>
            );
          })}
        </dl>
      )}
    </div>
  );
}
