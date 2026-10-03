import { Help } from "@/components/help";
import { metricLabel } from "@/lib/format";
import { GLOSSARY, metricMeaning, type Term as Key } from "@/lib/glossary";
import { cn } from "@/lib/utils";

/** A label with its glossary entry behind a ?. */
export function Term({
  k,
  children,
  className,
}: {
  k: Key;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {children}
      <Help label={`What is ${typeof children === "string" ? children : k}?`}>{GLOSSARY[k]}</Help>
    </span>
  );
}

/** A scorer/metric key as `scorer · metric`, with what it measures behind a ? when loupe knows. */
export function MetricName({ k, className }: { k: string; className?: string }) {
  const meaning = metricMeaning(k);
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap", className)}>
      {metricLabel(k)}
      {meaning && <Help label={`What is ${metricLabel(k)}?`}>{meaning}</Help>}
    </span>
  );
}
