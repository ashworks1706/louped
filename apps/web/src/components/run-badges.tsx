import { Badge } from "@/components/ui/badge";
import type { RunSummary } from "@/lib/api";

export function KindBadge({ kind }: { kind: RunSummary["kind"] }) {
  return <Badge variant="outline">{kind}</Badge>;
}

export function StatusDot({ status }: { status: string }) {
  const tone =
    status === "success" || status === "finished"
      ? "bg-positive"
      : status === "error" || status === "failed"
        ? "bg-negative"
        : "bg-muted-foreground/60";
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
      <span className={`size-1.5 rounded-full ${tone}`} />
      {status}
    </span>
  );
}
