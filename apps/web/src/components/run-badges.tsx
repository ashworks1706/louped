import { Badge } from "@/components/ui/badge";
import { isLive, type RunSummary } from "@/lib/api";

export function KindBadge({ kind }: { kind: RunSummary["kind"] }) {
  return <Badge variant="outline">{kind}</Badge>;
}

/** Where an imported run ran (sol, slurm, vm); nothing for a run made here. */
export function HostBadge({ host }: { host?: string | null }) {
  if (!host) return null;
  return (
    <Badge variant="outline" className="font-mono" title={`Ran on ${host}, imported`}>
      {host}
    </Badge>
  );
}

/** A run made on a cohort, part of the experiment's items (louped.tracking.cohort_ids). */
export function CohortBadge({ tags }: { tags: Record<string, string> }) {
  const name = tags["louped.cohort"];
  if (!name) return null;
  const n = tags["louped.cohort_n"];
  return (
    <Badge
      variant="outline"
      className="font-mono"
      title={`Ran on cohort ${name}${n ? `, ${n} items` : ""}, not every item`}
    >
      cohort {name}
      {n && ` · ${n}`}
    </Badge>
  );
}

/** What looked degenerate in a training run: its data's flags and its early numbers
 * (louped.train.alarms), each with its step. */
export function AlarmBadge({ tags }: { tags: Record<string, string> }) {
  const text = tags["louped.alarm"];
  if (!text) return null;
  return (
    <Badge
      variant="outline"
      className="border-negative/50 text-negative max-w-xl truncate"
      title={text.split("; ").join("\n")}
    >
      alarm · {text}
    </Badge>
  );
}

/** A run's status; a live one pulses and shows how many samples are done. */
export function StatusDot({
  status,
  samples,
  total,
}: {
  status: string;
  samples?: number | null;
  total?: number | null;
}) {
  const live = isLive(status);
  // Inspect says success and MLflow finished for the same thing: one word for it everywhere
  const done = status === "success" || status === "finished" || status === "succeeded";
  const tone = live
    ? "bg-foreground motion-safe:animate-pulse"
    : done
      ? "bg-positive"
      : status === "error" || status === "failed"
        ? "bg-negative"
        : "bg-muted-foreground/60";
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span className={`size-1.5 rounded-full ${tone}`} />
      {live && status !== "queued" && status !== "submitted"
        ? "running"
        : status === "exported"
          ? "awaiting result"
          : done
            ? "finished"
            : status}
      {live && samples != null && total ? (
        <span className="font-mono tabular-nums">
          {samples}/{total}
        </span>
      ) : null}
    </span>
  );
}
