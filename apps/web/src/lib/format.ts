/** The standard error logged next to a scorer/metric key, if any. */
export function stderr(metrics: Record<string, number>, key: string): number | null {
  return key.includes("/")
    ? (metrics[`${key.slice(0, key.lastIndexOf("/"))}/stderr`] ?? null)
    : null;
}

/** Headline metrics: everything except the error bars, which are shown next to their metric. */
export function headline(metrics: Record<string, number>): [string, number, number | null][] {
  return Object.entries(metrics)
    .filter(([k]) => !k.endsWith("/stderr") && !k.endsWith("/std"))
    .map(([k, v]) => [k, v, stderr(metrics, k)]);
}

export function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Number.isInteger(v)) return v.toString();
  return v.toFixed(digits);
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

/** `scorer/metric` shown as `scorer · metric`. */
export function metricLabel(key: string): string {
  const [scorer, metric] = key.split("/");
  return metric ? `${scorer} · ${metric}` : key;
}

const units: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31536000],
  ["month", 2592000],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return fmt.format(Math.round(seconds / size), unit);
  }
  return "just now";
}
