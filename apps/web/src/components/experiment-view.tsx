"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical, Rocket } from "lucide-react";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";

import { EmptyState } from "@/components/empty-state";
import { StatusLabel } from "@/components/experiments-list";
import { Markdown } from "@/components/markdown";
import { QueryState } from "@/components/query-state";
import { RunsTable } from "@/components/runs-table";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isLive, q, type ExperimentDetail, type Launchable } from "@/lib/api";
import { ago } from "@/lib/format";

const AXIS_TITLE: Record<ExperimentDetail["axis"], string> = {
  behavior: "Behavior & alignment",
  efficiency: "Efficiency & systems",
  checks: "Instrument checks",
};

/** One research question: what it asks, how it is tested, what it found, its runs, and what
 * launches it. */
export function ExperimentView() {
  const [name] = useQueryState("name", parseAsString);
  if (!name) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={FlaskConical}
          title="No experiment selected"
          body="Open one from Experiments, or start one."
          action={{ href: "/launch/?id=new", label: "New experiment" }}
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
    <>
      <ExperimentHeader experiment={e} />
      <section className="mx-auto max-w-6xl px-6 py-6">
        <ExperimentTabs experiment={e} />
      </section>
    </>
  );
}

function ExperimentHeader({ experiment: e }: { experiment: ExperimentDetail }) {
  const live = e.runs.filter((r) => isLive(r.status)).length;
  const last = e.runs[0];
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6">
        <Link
          href="/experiments/"
          className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
        >
          <ArrowLeft className="size-3" /> Experiments
        </Link>
        <div className="flex flex-col items-start gap-x-6 gap-y-3 sm:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-mono text-xl font-semibold tracking-tight">{e.name}</h1>
              <StatusLabel status={e.status} />
            </div>
            <p className="max-w-3xl text-[15px] leading-snug font-medium">
              {e.question ?? "No question written yet. Add one under ## Question in its README."}
            </p>
          </div>
          <LaunchActions name={e.name} />
        </div>
        <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt>Axis</dt>
            <dd className="text-foreground">{AXIS_TITLE[e.axis]}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Domain</dt>
            <dd className="text-foreground">{e.domain_title}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Runs</dt>
            <dd className="text-foreground font-mono tabular-nums">
              {e.runs.length}
              {live > 0 && ` · ${live} live`}
            </dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Last run</dt>
            <dd className="text-foreground">{last ? ago(last.created) : "never"}</dd>
          </div>
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
        <Button key={l.id} asChild size="sm" variant={i === 0 ? "default" : "outline"}>
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
function firstRun(name: string, own: Launchable[]): { href: string; label: string } {
  const first = own[0];
  if (first)
    return {
      href: `/launch/?id=${encodeURIComponent(first.id)}`,
      label: `Launch ${first.title.slice(name.length + 1)}`,
    };
  return { href: `/experiment/?name=${encodeURIComponent(name)}&tab=design`, label: "How it runs" };
}

const TABS = ["design", "runs"] as const;

function ExperimentTabs({ experiment: e }: { experiment: ExperimentDetail }) {
  const own = useOwnLaunchables(e.name);
  const [tab, setTab] = useQueryState("tab", parseAsStringLiteral(TABS).withDefault("design"));
  return (
    <Tabs value={tab} onValueChange={(v) => void setTab(v as (typeof TABS)[number])}>
      <TabsList>
        <TabsTrigger value="design">Design and result</TabsTrigger>
        <TabsTrigger value="runs" aria-label={`Runs (${e.runs.length})`}>
          Runs
          <span className="text-muted-foreground ml-1.5 font-mono text-[11px] tabular-nums">
            {e.runs.length}
          </span>
        </TabsTrigger>
      </TabsList>
      <TabsContent value="design">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <article className="max-w-3xl min-w-0">
            <Markdown>{e.readme}</Markdown>
          </article>
          <aside className="order-first flex flex-col gap-3 lg:sticky lg:top-6 lg:order-none lg:self-start">
            <h2 className="text-muted-foreground text-xs font-medium">Result</h2>
            <p className="text-sm leading-relaxed">
              {e.result ?? "Not written yet. It goes under ## Result in the README."}
            </p>
            <p className="text-muted-foreground text-xs">
              Edit <span className="font-mono">experiments/{e.name}/README.md</span>; this page
              reads it.
            </p>
          </aside>
        </div>
      </TabsContent>
      <TabsContent value="runs">
        {e.runs.length === 0 ? (
          <EmptyState
            icon={Rocket}
            title="No runs yet"
            body="Nothing has run under it yet."
            action={firstRun(e.name, own)}
          />
        ) : (
          <RunsTable runs={e.runs} byExperiment={false} />
        )}
      </TabsContent>
    </Tabs>
  );
}
