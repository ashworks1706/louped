"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Cloud,
  CloudDownload,
  CloudUpload,
  Rocket,
  Sparkles,
  Square,
  Terminal,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { parseAsString, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { DeleteButton } from "@/components/delete-button";
import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { Part, part, partId, useRules } from "@/components/parts";
import { askToNotify } from "@/components/notifier";
import { QueryState } from "@/components/query-state";
import { KindBadge, StatusDot } from "@/components/run-badges";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  ApiError,
  cancelJob,
  connectRemote,
  deleteJob,
  importResult,
  isLive,
  launch,
  pullRuns,
  pushRuns,
  q,
  type Job,
} from "@/lib/api";
import { ago } from "@/lib/format";
import { jobHref, runHref } from "@/lib/href";
import { cn } from "@/lib/utils";

/** How far a job has got, read from its log: the last `[k/n]` a script prints for its own
 * steps, else the last tqdm bar. Null when the log says nothing countable. */
export function progress(log: string): { done: number; total: number; label: string } | null {
  const steps = [...log.matchAll(/^\[(\d+)\/(\d+)\]\s*(.*)$/gm)].at(-1);
  if (steps) return { done: Number(steps[1]), total: Number(steps[2]), label: steps[3] };
  const bar = [...log.matchAll(/(\d+)%\|[^|\n]*\|\s*(\d+)\/(\d+)/g)].at(-1);
  if (bar) return { done: Number(bar[2]), total: Number(bar[3]), label: "" };
  return null;
}

/** Seconds as 4s, 2m 05s, 1h 02m. */
function span(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}

/** How long a job has run: to now while live, ticking once a second. */
function useElapsed(job: Job) {
  const [now, setNow] = useState(() => Date.now());
  const live = isLive(job.status);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [live]);
  if (!job.started) return null;
  const end = job.ended ? Date.parse(job.ended) : now;
  return span((end - Date.parse(job.started)) / 1000);
}

/** A bar: filled to done/total when known, a moving sliver while running without a count. */
export function ProgressBar({ job, log }: { job: Job; log?: string }) {
  const p = log ? progress(log) : null;
  const live = isLive(job.status);
  const ended = !live && job.status !== "exported";
  const pct = ended ? 100 : p && p.total > 0 ? Math.min(100, (100 * p.done) / p.total) : null;
  return (
    <div
      role="progressbar"
      aria-label={`${job.title} progress`}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
      className="bg-muted relative h-1.5 w-full overflow-hidden rounded-full"
    >
      {pct != null ? (
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            job.status === "failed"
              ? "bg-negative"
              : job.status === "succeeded"
                ? "bg-positive"
                : "bg-foreground",
          )}
          style={{ width: `${pct}%` }}
        />
      ) : live && job.status === "running" ? (
        <div className="bg-foreground absolute inset-y-0 w-1/4 rounded-full motion-safe:animate-[slide_1.4s_ease-in-out_infinite]" />
      ) : null}
    </div>
  );
}

/** The queue on the Runs page: what is running and what ran, each opening its log. */
export function JobsPanel() {
  const rule = useRules();
  const health = useQuery(q.health());
  const jobs = useQuery({ ...q.jobs(), enabled: health.data?.launching === true });
  if (health.data?.launching !== true) return null;
  const list = jobs.data ?? [];
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-medium" {...part("runs/heading/jobs")}>
          Jobs
          <Help label="What is a job?">
            A command started from Launch. Jobs run one at a time, in the order launched; the runs
            each one writes appear in the table below as they are written.
          </Help>
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Sync />
          <ImportResult />
          <Button
            asChild
            variant="outline"
            size="sm"
            {...part("runs/action/launch")}
            className={cn(rule("runs/action/launch").hidden && "hidden")}
          >
            <Link href="/launch/">
              <Rocket /> Launch
            </Link>
          </Button>
        </div>
      </div>
      {list.length === 0 ? (
        <p className="text-muted-foreground rounded-xl border border-dashed px-4 py-5 text-center text-sm">
          Nothing launched yet.
        </p>
      ) : (
        <div className="divide-y rounded-xl border">
          {list.slice(0, 8).map((j) => (
            <JobRow key={j.id} job={j} />
          ))}
        </div>
      )}
    </section>
  );
}

function JobRow({ job }: { job: Job }) {
  const live = isLive(job.status);
  // The log is polled only for the job that is running, for its progress.
  const detail = useQuery({ ...q.job(job.id), enabled: job.status === "running" });
  const elapsed = useElapsed(job);
  const p = detail.data ? progress(detail.data.log) : null;
  return (
    <Link
      href={jobHref(job.id)}
      {...part(partId("runs/job", job.id))}
      className="hover:bg-accent/40 flex flex-col gap-2 px-4 py-3 transition-colors"
    >
      <div className="flex items-center gap-3">
        <span className="min-w-0 flex-1 truncate font-mono text-xs">{job.title}</span>
        {p && live && (
          <span className="text-muted-foreground font-mono text-[11px] tabular-nums">
            {p.done}/{p.total}
          </span>
        )}
        <StatusDot status={job.status} />
        <span className="text-muted-foreground w-16 text-right font-mono text-[11px] tabular-nums">
          {elapsed ?? ""}
        </span>
        <span className="text-muted-foreground w-24 text-right text-xs whitespace-nowrap">
          {ago(job.created)}
        </span>
      </div>
      {live && <ProgressBar job={job} log={detail.data?.log} />}
    </Link>
  );
}

/** One job: its state, progress and command, the runs it wrote, and its log as it streams. */
export function JobView() {
  const [id] = useQueryState("id", parseAsString);
  if (!id) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={Terminal}
          title="No job selected"
          action={{ href: "/runs/", label: "Runs" }}
        />
      </section>
    );
  }
  return <JobLoaded id={id} />;
}

function JobLoaded({ id }: { id: string }) {
  const job = useQuery(q.job(id));
  const client = useQueryClient();
  const wasLive = useRef<boolean | null>(null);
  const status = job.data?.status;
  useEffect(() => {
    // A job that ends has written its runs: refresh the lists that show them.
    if (status == null) return;
    if (wasLive.current && !isLive(status)) {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["vectors"] });
      void client.invalidateQueries({ queryKey: ["graphs"] });
    }
    wasLive.current = isLive(status);
  }, [client, status]);
  const stop = useMutation({
    mutationFn: cancelJob,
    meta: { action: "Cancel" },
    onSuccess: () => void client.invalidateQueries({ queryKey: ["job", id] }),
  });
  if (!job.data) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <QueryState query={job}>{() => null}</QueryState>
      </section>
    );
  }
  const j = job.data;
  const p = progress(j.log);
  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-6">
          <Link
            href="/runs/"
            {...part("job/back")}
            className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
          >
            <ArrowLeft className="size-3" /> Runs
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h1
              className="min-w-0 truncate font-mono text-xl font-semibold tracking-tight"
              {...part("job/title")}
            >
              {j.title}
            </h1>
            <StatusDot status={j.status} />
            <div className="ml-auto flex gap-2" {...part("job/actions")}>
              {isLive(j.status) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => stop.mutate(j.id)}
                  disabled={stop.isPending}
                >
                  <Square /> Stop
                </Button>
              )}
              <DeleteButton
                what="job"
                name={j.title}
                undo="It and its log move to .louped/trash/jobs. The runs it wrote stay."
                remove={() => deleteJob(j.id)}
                then="/runs/"
                disabled={isLive(j.status) ? "Still running: stop it first" : undefined}
              />
            </div>
          </div>
          <JobFacts job={j} step={p?.label} />
          <ProgressBar job={j} log={j.log} />
        </div>
      </header>
      <section className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-6">
        <div
          className="bg-muted/50 flex items-start gap-2 rounded-lg border py-1 pr-1 pl-3"
          {...part("job/command")}
        >
          <code className="flex-1 py-1.5 font-mono text-xs [overflow-wrap:anywhere]">
            <span className="text-muted-foreground select-none">$ </span>
            {j.argv.join(" ")}
          </code>
          <CopyButton text={j.argv.join(" ")} />
        </div>
        <RunLinks log={j.log} />
        <Log log={j.log} live={isLive(j.status)} />
      </section>
    </>
  );
}

function JobFacts({ job, step }: { job: Job; step?: string }) {
  const elapsed = useElapsed(job);
  return (
    <dl
      className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm"
      {...part("job/facts")}
    >
      <div className="flex gap-1.5">
        <dt>Started</dt>
        <dd className="text-foreground">{job.started ? ago(job.started) : "waiting in queue"}</dd>
      </div>
      {elapsed && (
        <div className="flex gap-1.5">
          <dt>{isLive(job.status) ? "Running for" : "Took"}</dt>
          <dd className="text-foreground font-mono tabular-nums">{elapsed}</dd>
        </div>
      )}
      {job.exit_code != null && (
        <div className="flex gap-1.5">
          <dt>Exit</dt>
          <dd className="text-foreground font-mono">{job.exit_code}</dd>
        </div>
      )}
      {step && isLive(job.status) && (
        <div className="flex min-w-0 gap-1.5">
          <dt>Now</dt>
          <dd className="text-foreground truncate">{step}</dd>
        </div>
      )}
    </dl>
  );
}

/** The log, following its end while live unless scrolled up. */
function Log({ log, live }: { log: string; live: boolean }) {
  const box = useRef<HTMLPreElement>(null);
  const pinned = useRef(true);
  useEffect(() => {
    if (pinned.current) box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [log]);
  return (
    <Part id="job/log" className="flex flex-col gap-2">
      <h2 className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
        Log
        {live && <span className="bg-foreground size-1.5 rounded-full motion-safe:animate-pulse" />}
      </h2>
      <pre
        ref={box}
        tabIndex={0}
        aria-label="Job log"
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
        }}
        className="bg-muted/40 focus-visible:ring-ring/30 h-[min(60vh,40rem)] overflow-auto rounded-lg border p-4 font-mono text-[11px] leading-[1.15rem] whitespace-pre-wrap outline-none focus-visible:ring-[3px]"
      >
        {log || "No output yet."}
      </pre>
    </Part>
  );
}

/** The runs a job's output names ("run": "m-…", as louped prints them), as links. */
function RunLinks({ log }: { log: string }) {
  const runs = useQuery(q.runs());
  const ids = [
    ...new Set(
      [...log.matchAll(/"(?:run|grid|analysis|training|bench)": "([em]-[\w-]+)"/g)].map(
        (m) => m[1],
      ),
    ),
  ];
  if (!ids.length) return null;
  return (
    <Part as="section" id="job/wrote" className="flex flex-col gap-2">
      <h2 className="text-muted-foreground text-xs font-medium">Wrote</h2>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {ids.map((id) => {
          const run = runs.data?.find((r) => r.id === id);
          return (
            <Link
              key={id}
              href={runHref(id)}
              {...part(partId("job/run", id))}
              className="hover:bg-accent/40 flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors"
            >
              <span className="min-w-0 flex-1 truncate">{run?.name ?? id}</span>
              {run && <KindBadge kind={run.kind} />}
            </Link>
          );
        })}
      </div>
    </Part>
  );
}

/** Push and Pull with the project's remote, when it has one. */
function Sync() {
  const rule = useRules();
  const client = useQueryClient();
  const health = useQuery(q.health());
  const remote = health.data?.remote;
  const [connecting, setConnecting] = useState(false);
  // a missing Hugging Face token opens Connect instead of an error
  const needsToken = (error: Error) => error instanceof ApiError && error.status === 401;
  const push = useMutation({
    mutationFn: pushRuns,
    meta: { action: "Push", quiet: needsToken },
    onError: (e) => needsToken(e) && setConnecting(true),
    onSuccess: (done) =>
      toast(done.bundle ? `${done.runs.length} runs pushed` : "Nothing new to push", {
        description: <span className="font-mono">{done.remote}</span>,
      }),
  });
  const pull = useMutation({
    mutationFn: pullRuns,
    meta: { action: "Pull", quiet: needsToken },
    onError: (e) => needsToken(e) && setConnecting(true),
    onSuccess: (found) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["runs"] });
      const runs = found.reduce((n, d) => n + d.runs.length, 0);
      toast(found.length ? `${runs} runs pulled` : "Nothing new to pull", {
        description: found.length
          ? `From ${[...new Set(found.map((d) => d.host))].join(", ")}`
          : remote,
      });
    },
  });
  return (
    <>
      {remote ? (
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => pull.mutate()}
            {...part("runs/action/pull")}
            className={cn(rule("runs/action/pull").hidden && "hidden")}
            disabled={pull.isPending}
            title={`Add the runs pushed to ${remote}`}
          >
            <CloudDownload /> Pull
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => push.mutate()}
            {...part("runs/action/push")}
            className={cn(rule("runs/action/push").hidden && "hidden")}
            disabled={push.isPending}
            title={`Push this louped's new runs to ${remote}`}
          >
            <CloudUpload /> Push
          </Button>
        </>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setConnecting(true)}
          {...part("runs/action/connect")}
          className={cn(rule("runs/action/connect").hidden && "hidden")}
          title="Share runs through a remote"
        >
          <Cloud /> Connect
        </Button>
      )}
      <Connect open={connecting} onOpenChange={setConnecting} remote={remote ?? ""} />
    </>
  );
}

/** Sets the remote runs are pushed to and pulled from, and a Hugging Face token for an hf:// one. */
function Connect({
  open,
  onOpenChange,
  remote,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  remote: string;
}) {
  const client = useQueryClient();
  const connect = useMutation({
    mutationFn: connectRemote,
    meta: { action: "Connect" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["health"] });
      onOpenChange(false);
      toast("Remote set", { description: <span className="font-mono">{done.remote}</span> });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">Connect a remote</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Where runs are pushed and pulled, saved in louped.toml. The token stays on this machine,
            where Hugging Face&apos;s own tools keep it.
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            connect.mutate({
              remote: String(form.get("remote") ?? ""),
              token: String(form.get("token") ?? ""),
            });
          }}
        >
          <label className="flex flex-col gap-1 text-xs">
            Remote
            <Input
              name="remote"
              defaultValue={remote}
              placeholder="Empty: a private HF bucket of your own"
              className="font-mono placeholder:font-sans"
              autoComplete="off"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span>
              Hugging Face token{" "}
              <a
                className="text-muted-foreground underline underline-offset-2"
                href="https://huggingface.co/settings/tokens"
                target="_blank"
                rel="noreferrer"
              >
                (write access)
              </a>
            </span>
            <Input
              name="token"
              type="password"
              placeholder="Empty if this machine is signed in"
              className="font-mono placeholder:font-sans"
              autoComplete="off"
            />
          </label>
          <Button type="submit" size="sm" className="self-end" disabled={connect.isPending}>
            Connect
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Takes the louped-result-….tar.gz an exported job wrote elsewhere; its runs join Runs. */
function ImportResult() {
  const rule = useRules();
  const client = useQueryClient();
  const router = useRouter();
  const picker = useRef<HTMLInputElement>(null);
  const bring = useMutation({
    mutationFn: importResult,
    meta: { action: "Import" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["runs"] });
      toast(`${done.runs.length} runs imported from ${done.host}`, {
        description: done.skipped.length ? `${done.skipped.length} were already here.` : undefined,
      });
      if (done.job) router.push(jobHref(done.job));
    },
  });
  return (
    <>
      <input
        ref={picker}
        type="file"
        accept=".gz,.tgz,application/gzip"
        className="hidden"
        aria-label="Result archive"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) bring.mutate(file);
          e.target.value = "";
        }}
      />
      <Button
        variant="ghost"
        size="sm"
        onClick={() => picker.current?.click()}
        {...part("runs/action/import")}
        className={cn(rule("runs/action/import").hidden && "hidden")}
        disabled={bring.isPending}
        title="The louped-result-….tar.gz a job exported to Sol, a cluster or a VM wrote"
      >
        <Upload /> Import result
      </Button>
    </>
  );
}

/** Starts `louped examples` and opens its job: example runs for every page, on a tiny model. */
export function ExamplesButton({ variant = "default" }: { variant?: "default" | "outline" }) {
  const router = useRouter();
  const client = useQueryClient();
  const go = useMutation({
    mutationFn: () => launch({ id: "examples", options: {} }),
    meta: { action: "Load examples" },
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      router.push(jobHref(job.id));
    },
  });
  return (
    <Button
      size="sm"
      variant={variant}
      onClick={() => {
        askToNotify();
        go.mutate();
      }}
      disabled={go.isPending}
    >
      <Sparkles /> Load examples
    </Button>
  );
}
