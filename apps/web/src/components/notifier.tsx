"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { isLive, q, type Job, type RunSummary } from "@/lib/api";
import { runHref } from "@/lib/href";

/** How often to look for runs started outside the app (a script, a terminal) while none is live:
 * slow, since listing runs reads every log. A run that starts and ends between two looks is not
 * announced. */
const IDLE_MS = 120_000;
const LIVE_MS = 3000;
/** A run that ends this soon after a job ended is taken to be that job's, and not announced. */
const JOB_GRACE_MS = 2 * LIVE_MS + 1000;

type Ended = {
  title: string;
  /** The job's command or the run's name, shown in mono. */
  id: string;
  body: React.ReactNode;
  /** The body as text, for a desktop notification. */
  text: string;
  href: string;
  outcome: "done" | "failed" | "stopped";
};

/** Asks once to notify when a job ends in the background. Call it from a click handler: browsers
 * ignore or quietly drop a request made outside one. */
export function askToNotify() {
  if (typeof Notification !== "undefined" && Notification.permission === "default")
    void Notification.requestPermission();
}

/** Watches launched jobs and runs, and says when one ends: a toast, and a desktop notification
 * when the window is not focused. Both poll in the background, since that is when a notice
 * matters. A run is not reported while a job is live or just after one ends, since a job's own
 * runs end inside it and the job's notice covers them. */
export function Notifier() {
  const router = useRouter();
  const health = useQuery(q.health());
  const jobs = useQuery({
    ...q.jobs(),
    retry: false,
    // Only a server that launches has jobs; an exposed one answers 403.
    enabled: health.data?.launching === true,
    refetchIntervalInBackground: true,
  });
  const runs = useQuery({
    ...q.runs(),
    refetchInterval: (query) =>
      query.state.data?.some((r) => isLive(r.status)) ? LIVE_MS : IDLE_MS,
    refetchIntervalInBackground: true,
  });
  const seenJobs = useRef<Map<string, string> | null>(null);
  const seenRuns = useRef<Map<string, string> | null>(null);
  const jobEndedAt = useRef(0);

  useEffect(() => {
    if (!jobs.data) return;
    const ended = transitions(seenJobs, jobs.data, (j) => j.status, jobEnded);
    if (ended.length > 0) jobEndedAt.current = Date.now();
    ended.forEach((e) => tell(e, router.push));
  }, [jobs.data, router]);

  useEffect(() => {
    if (!runs.data) return;
    const ended = transitions(seenRuns, runs.data, (r) => r.status, runEnded);
    const jobLive = jobs.data?.some((j) => isLive(j.status)) ?? false;
    const byJob = jobLive || Date.now() - jobEndedAt.current < JOB_GRACE_MS;
    if (!byJob) ended.forEach((e) => tell(e, router.push));
  }, [runs.data, jobs.data, router]);

  return null;
}

/** The items that went from live to ended since the last look. The first look only records, so
 * what had already ended when the page opened is not announced. */
function transitions<T extends { id: string }>(
  seen: React.RefObject<Map<string, string> | null>,
  items: T[],
  status: (item: T) => string,
  describe: (item: T) => Ended,
): Ended[] {
  const before = seen.current;
  seen.current = new Map(items.map((i) => [i.id, status(i)]));
  if (!before) return [];
  return items.filter((i) => isLive(before.get(i.id) ?? "") && !isLive(status(i))).map(describe);
}

function jobEnded(job: Job): Ended {
  const href = `/launch/?job=${encodeURIComponent(job.id)}`;
  const base = { id: job.title, href };
  // A job the server found mid-run when it restarted is saved failed, with no exit code.
  if (job.exit_code == null && job.status === "failed")
    return {
      ...base,
      title: "Job lost",
      body: "The server restarted before it ended.",
      text: "The server restarted before it ended.",
      outcome: "failed",
    };
  const took =
    job.started && job.ended && job.ended !== job.started
      ? ` in ${duration(job.started, job.ended)}`
      : "";
  if (job.status === "succeeded")
    return {
      ...base,
      title: "Job finished",
      body: <Mono>exit 0{took}</Mono>,
      text: `exit 0${took}`,
      outcome: "done",
    };
  if (job.status === "cancelled")
    return {
      ...base,
      title: "Job cancelled",
      body: <Mono>stopped{took}</Mono>,
      text: `stopped${took}`,
      outcome: "stopped",
    };
  return {
    ...base,
    title: "Job failed",
    text: `exit ${job.exit_code}${took}`,
    body: (
      <>
        <Mono>
          exit {job.exit_code}
          {took}
        </Mono>
        . The log is on the Launch page.
      </>
    ),
    outcome: "failed",
  };
}

function runEnded(run: RunSummary): Ended {
  const s = run.status.toLowerCase();
  const kind = run.kind[0].toUpperCase() + run.kind.slice(1);
  const base = {
    id: run.experiment ? `${run.experiment} · ${run.name}` : run.name,
    href: runHref(run.id),
    text: `Status ${run.status}.`,
    body: (
      <>
        Status <Mono>{run.status}</Mono>.
      </>
    ),
  };
  if (s === "error" || s === "failed")
    return { ...base, title: `${kind} failed`, outcome: "failed" };
  if (s === "cancelled" || s === "killed")
    return { ...base, title: `${kind} stopped`, outcome: "stopped" };
  return { ...base, title: `${kind} finished`, outcome: "done" };
}

function tell(e: Ended, go: (href: string) => void) {
  const title = (
    <span className="flex flex-col">
      <span>{e.title}</span>
      <span className="font-mono text-xs font-normal">{e.id}</span>
    </span>
  );
  const options = {
    description: e.body,
    action: { label: "Open", onClick: () => go(e.href) },
    // A failure stays until dismissed; the rest step aside.
    duration: e.outcome === "failed" ? Infinity : 8000,
  };
  if (e.outcome === "failed") toast.error(title, options);
  else if (e.outcome === "done") toast.success(title, options);
  else toast(title, options);

  if (
    typeof Notification !== "undefined" &&
    Notification.permission === "granted" &&
    !document.hasFocus()
  ) {
    const n = new Notification(`${e.title}: ${e.id}`, { body: e.text, tag: e.href });
    n.onclick = () => {
      window.focus();
      go(e.href);
    };
  }
}

function Mono({ children }: { children: React.ReactNode }) {
  return <span className="font-mono tabular-nums">{children}</span>;
}

function duration(start: string, end: string): string {
  const s = Math.round((Date.parse(end) - Date.parse(start)) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}
