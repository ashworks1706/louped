import { num } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A number with its standard error, mono and right-aligned. */
export function MetricValue({
  value,
  err,
  className,
}: {
  value: number | null | undefined;
  err?: number | null;
  className?: string;
}) {
  return (
    <span className={cn("font-mono tabular-nums", className)}>
      {num(value)}
      {err !== null && err !== undefined && (
        <span className="text-muted-foreground"> ±{num(err, 2)}</span>
      )}
    </span>
  );
}

/** One sample's score: pass and fail as glyphs, anything else as a number. */
export function ScoreCell({ value }: { value: number | null | undefined }) {
  if (value === 1) return <span className="text-positive font-mono">✓</span>;
  if (value === 0) return <span className="text-negative font-mono">✗</span>;
  return <span className="font-mono tabular-nums">{num(value)}</span>;
}

export function Delta({ value }: { value: number }) {
  const tone = value > 0 ? "text-positive" : value < 0 ? "text-negative" : "text-muted-foreground";
  return (
    <span className={cn("font-mono tabular-nums", tone)}>
      {value > 0 ? "+" : ""}
      {num(value)}
    </span>
  );
}
