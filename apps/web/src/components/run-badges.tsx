import { Badge } from "@/components/ui/badge";
import { isLive, type RunSummary } from "@/lib/api";

export function KindBadge({ kind }: { kind: RunSummary["kind"] }) {
  return <Badge variant="outline">{kind}</Badge>;
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
  const tone = live
    ? "bg-foreground motion-safe:animate-pulse"
    : status === "success" || status === "finished" || status === "succeeded"
      ? "bg-positive"
      : status === "error" || status === "failed"
        ? "bg-negative"
        : "bg-muted-foreground/60";
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span className={`size-1.5 rounded-full ${tone}`} />
      {live && status !== "queued" ? "running" : status}
      {live && samples != null && total ? (
        <span className="font-mono tabular-nums">
          {samples}/{total}
        </span>
      ) : null}
    </span>
  );
}
