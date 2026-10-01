import Link from "next/link";

import { cn } from "@/lib/utils";

/** Numbers in bordered cells, any count: each cell draws its own right and bottom border and the
 * grid clips the outer ones, so a part-filled last row leaves plain background, not a grey gap. */
export function StatGrid({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid overflow-hidden rounded-xl border sm:grid-cols-2 lg:grid-cols-4",
        "[&>*]:-mr-px [&>*]:-mb-px [&>*]:border-r [&>*]:border-b",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** One cell: a label, the number, and an optional line under it. */
export function Stat({
  label,
  children,
  note,
  href,
}: {
  label: string;
  children: React.ReactNode;
  note?: React.ReactNode;
  href?: string;
}) {
  const body = (
    <>
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="font-mono text-2xl font-medium tabular-nums">{children}</span>
      {note && <span className="text-muted-foreground text-xs">{note}</span>}
    </>
  );
  return href ? (
    <Link
      href={href}
      className="hover:bg-accent/40 focus-visible:ring-ring/50 flex flex-col gap-1 p-4 transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
    >
      {body}
    </Link>
  ) : (
    <div className="flex flex-col gap-1 p-4">{body}</div>
  );
}
