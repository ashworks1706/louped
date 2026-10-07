"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical, Rocket } from "lucide-react";
import Link from "next/link";
import { parseAsString, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { arrange, part, partId, PartScope, useRules } from "@/components/parts";
import { StatusLabel } from "@/components/experiments-list";
import { EditableText } from "@/components/markdown-editor";
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
import { QueryState } from "@/components/query-state";
import { Figure } from "@/components/run-views";
import { ExperimentReports } from "@/components/reports-view";
import { RunsTable } from "@/components/runs-table";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  deleteExperiment,
  isLive,
  q,
  readme,
  saveReadme,
  type ExperimentDetail,
  type Launchable,
} from "@/lib/api";
import { ago } from "@/lib/format";
import { cn } from "@/lib/utils";
import { axisPath, experimentHref } from "@/lib/href";

const AXIS_TITLE: Record<ExperimentDetail["axis"], string> = {
  behavior: "Behavior & alignment",
  efficiency: "Efficiency & systems",
  checks: "Instrument checks",
};

/** One research question: what it asks, how it is tested, what it found, its runs, and what
 * launches it. */
export function ExperimentView({ axis }: { axis: "behavior" | "efficiency" }) {
  const [name] = useQueryState("name", parseAsString);
  if (!name) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={FlaskConical}
          title="No experiment selected"
          body="Open one from this domain's experiments."
          action={{ href: `/${axis}/experiments/`, label: "Experiments" }}
        />
      </section>
    );
  }
  return <ExperimentLoaded name={name} />;
}

function ExperimentLoaded({ name }: { name: string }) {
  const experiment = useQuery(q.experiment(name));
  // Runs come from the shared runs query, which already polls while one is live, so this page
  // does not read every log again on its own timer.
  const runs = useQuery(q.runs());
  if (!experiment.data) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <QueryState query={experiment}>{() => null}</QueryState>
      </section>
    );
  }
  const e = {
    ...experiment.data,
    runs: runs.data ? runs.data.filter((r) => r.experiment === name) : experiment.data.runs,
  };
  return (
    <PartScope experiment={name}>
      <ExperimentHeader experiment={e} />
      <section className="mx-auto max-w-6xl px-6 py-6">
        <ExperimentTabs experiment={e} />
      </section>
    </PartScope>
  );
}

function ExperimentHeader({ experiment: e }: { experiment: ExperimentDetail }) {
  const live = e.runs.filter((r) => isLive(r.status)).length;
  const last = e.runs[0];
  const rule = useRules();
  const meta: { name: string; label: string; value: React.ReactNode; className?: string }[] = [
    { name: "axis", label: "Axis", value: AXIS_TITLE[e.axis] },
    { name: "domain", label: "Domain", value: e.domain_title },
    {
      name: "runs",
      label: "Runs",
      value: `${e.runs.length}${live > 0 ? ` · ${live} live` : ""}`,
      className: "font-mono tabular-nums",
    },
    { name: "last-run", label: "Last run", value: last ? ago(last.created) : "never" },
  ];
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6">
        <Link
          href={`${axisPath(e.axis)}/experiments/`}
          className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
          {...part("experiment/back")}
        >
          <ArrowLeft className="size-3" /> Experiments
        </Link>
        <div className="flex flex-col items-start gap-x-6 gap-y-3 sm:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1
                className="font-mono text-xl font-semibold tracking-tight"
                {...part("experiment/title")}
              >
                {e.name}
              </h1>
              <span {...part("experiment/status")} className="inline-flex">
                <StatusLabel status={e.status} />
              </span>
            </div>
            <p
              className="max-w-3xl text-[15px] leading-snug font-medium"
              {...part("experiment/question")}
            >
              {e.question ?? "No question written yet. Add one under ## Question in its README."}
            </p>
          </div>
          <div className="flex items-start gap-2">
            <LaunchActions name={e.name} />
            <span
              {...part("experiment/delete")}
              className={cn(rule("experiment/delete").hidden && "hidden")}
            >
              <DeleteButton
                what="experiment"
                name={e.name}
                undo={`Its folder moves to .louped/trash/experiments; move it back to experiments/ to restore it. Its ${e.runs.length} runs stay.`}
                remove={() => deleteExperiment(e.name)}
                then={`${axisPath(e.axis)}/experiments/`}
              />
            </span>
          </div>
        </div>
        <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {arrange(meta, (m) => partId("experiment/meta", m.name), rule).map((m) => {
            const r = rule(partId("experiment/meta", m.name));
            return (
              <div
                key={m.name}
                className="flex gap-1.5"
                {...part(partId("experiment/meta", m.name))}
              >
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

/** The experiment's own scripts and training configs, each opening its Launch form. Absent on
 * a server that does not launch. */
function LaunchActions({ name }: { name: string }) {
  const own = useOwnLaunchables(name);
  if (own.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {own.map((l, i) => (
        <Button
          key={l.id}
          asChild
          size="sm"
          variant={i === 0 ? "default" : "outline"}
          {...part(partId("experiment/launch", l.title.slice(name.length + 1)))}
        >
          <Link href={`/launch/?id=${encodeURIComponent(l.id)}`}>
            <Rocket />
            <span className="font-mono">{l.title.slice(name.length + 1)}</span>
          </Link>
        </Button>
      ))}
    </div>
  );
}

function useOwnLaunchables(name: string): Launchable[] {
  const launchables = useQuery(q.launchables());
  // run.py first: it is what answers the question; data and eval scripts are its parts.
  return (launchables.data ?? [])
    .filter((l) => l.id.startsWith(`script:${name}/`) || l.id.startsWith(`train:${name}/`))
    .sort((a, b) => Number(b.title.endsWith("/run.py")) - Number(a.title.endsWith("/run.py")));
}

/** The Launch form of the experiment's first script or config; without a launching server, its
 * design, whose Run section says how it runs. */
function firstRun(
  name: string,
  axis: ExperimentDetail["axis"],
  own: Launchable[],
): { href: string; label: string } {
  const first = own[0];
  if (first)
    return {
      href: `/launch/?id=${encodeURIComponent(first.id)}`,
      label: `Launch ${first.title.slice(name.length + 1)}`,
    };
  return { href: experimentHref(name, axis, "design"), label: "How it runs" };
}

function ExperimentTabs({ experiment: e }: { experiment: ExperimentDetail }) {
  const own = useOwnLaunchables(e.name);
  const client = useQueryClient();
  const layout = useLayout(e.name);
  const plugins = useQuery(q.plugins());
  const figures = useQuery(q.experimentViews(e.name));
  const rule = useRules();
  const [chosen, setTab] = useQueryState("tab", parseAsString);
  if (!layout.data) return <QueryState query={layout}>{() => null}</QueryState>;
  const at = (path: string) => partId("experiment/view", path);
  const shownViews = arrange(figures.data ?? [], (v) => at(v.path), rule);
  const views = (
    <div className="flex flex-col gap-4">
      {shownViews.map((v) => (
        <Figure
          key={v.path}
          view={v.view}
          id={at(v.path)}
          source={`experiment:${e.name}/${v.path}`}
        />
      ))}
    </div>
  );
  /** One of the experiment's figures by its path, or what is missing. */
  const one = (path: string) => {
    const v = figures.data?.find((f) => f.path === path);
    if (v)
      return <Figure view={v.view} id={at(v.path)} source={`experiment:${e.name}/${v.path}`} />;
    if (figures.isError)
      return <p className="text-muted-foreground text-sm">{figures.error.message}</p>;
    return figures.isPending ? null : (
      <p className="text-muted-foreground text-sm">
        No figure{" "}
        <span className="font-mono">
          experiments/{e.name}/{path}
        </span>
        .
      </p>
    );
  };
  const runs =
    e.runs.length === 0 ? (
      <EmptyState
        icon={Rocket}
        title="No runs yet"
        body="Nothing has run under it yet."
        action={firstRun(e.name, e.axis, own)}
      />
    ) : (
      <RunsTable runs={e.runs} byExperiment={false} />
    );
  const design = (
    <RegionGrid
      region="experiment.design"
      blocks={layout.data.regions["experiment.design"]}
      render={(b) => {
        switch (b.block) {
          case "readme":
            return {
              body: (
                <article className="max-w-3xl min-w-0">
                  <EditableText
                    name="README.md"
                    shown={e.readme}
                    source={() => readme(e.name)}
                    save={async (text) => {
                      await saveReadme(e.name, text);
                      await client.invalidateQueries({ queryKey: ["experiment", e.name] });
                      await client.invalidateQueries({ queryKey: ["experiments"] });
                    }}
                  />
                </article>
              ),
            };
          case "result":
            return {
              title: "Result",
              body: (
                <>
                  <p className="text-sm leading-relaxed">
                    {e.result ?? "Not written yet. It goes under ## Result in the README."}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    From <span className="font-mono">experiments/{e.name}/README.md</span>.
                  </p>
                </>
              ),
            };
          case "runs":
            return { title: "Runs", body: runs };
          case "reports":
            return { title: "Reports", body: <ExperimentReports name={e.name} /> };
          case "views":
            return shownViews.length ? { body: views } : null;
          case "view":
            return { body: one(b.path!) };
          case "plugin":
            return {
              body: <PluginBlock b={b} page="experiment.html" query={{ experiment: e.name }} />,
            };
          default:
            return null;
        }
      }}
    />
  );
  const tabs = layout.data.regions["experiment.tabs"].flatMap((b, at) => {
    const tab =
      b.block === "text"
        ? { value: `t-${at}`, label: "Notes", ...textBlock(b) }
        : b.block === "design"
          ? { value: "design", label: "Design and result", body: design }
          : b.block === "runs"
            ? { value: "runs", label: "Runs", body: runs, count: e.runs.length }
            : b.block === "reports"
              ? { value: "reports", label: "Reports", body: <ExperimentReports name={e.name} /> }
              : b.block === "views"
                ? { value: "views", label: "Figures", body: views, count: shownViews.length }
                : b.block === "view"
                  ? {
                      value: `v-${b.path}`,
                      label: figures.data?.find((f) => f.path === b.path)?.view.title ?? b.path!,
                      body: one(b.path!),
                    }
                  : b.block === "plugin"
                    ? {
                        value: `x-${b.plugin}`,
                        label: plugins.data?.find((p) => p.name === b.plugin)?.title ?? b.plugin!,
                        body: (
                          <PluginFrame
                            name={b.plugin!}
                            page={b.page ?? "experiment.html"}
                            query={{ experiment: e.name }}
                          />
                        ),
                      }
                    : null;
    return tab ? [{ count: undefined, ...tab, b, at, label: b.title ?? tab.label }] : [];
  });
  const tab = chosen && tabs.some((t) => t.value === chosen) ? chosen : tabs[0]?.value;
  return (
    <>
      <LayoutErrors page={layout.data} />
      <Tabs value={tab} onValueChange={(v) => void setTab(v)}>
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger
              key={t.value}
              value={t.value}
              data-part={blockId("experiment.tabs", t.b, t.at)}
              aria-label={t.count !== undefined ? `${t.label} (${t.count})` : undefined}
            >
              {t.label}
              {t.count !== undefined && (
                <span className="text-muted-foreground ml-1.5 font-mono text-[11px] tabular-nums">
                  {t.count}
                </span>
              )}
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
