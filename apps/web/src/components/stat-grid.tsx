"use client";

import Link from "next/link";

import { Help } from "@/components/help";
import { part as partProps, PartNote, useRules } from "@/components/parts";
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

/** One cell: a label, the number, and an optional line under it. With part, its address: the
 * layout can rename it, explain it, add a note under it or hide it. */
export function Stat({
  label,
  children,
  note,
  about,
  href,
  part,
}: {
  label: string;
  children: React.ReactNode;
  note?: React.ReactNode;
  /** What the number means, behind a ?; the layout's about wins. */
  about?: string;
  href?: string;
  part?: string;
}) {
  const rule = useRules();
  const r = part ? rule(part) : {};
  if (r.hidden) return null;
  const meaning = r.about ?? about;
  const body = (
    <>
      <span className="text-muted-foreground flex items-center gap-1 text-xs">
        {r.label ?? label}
        {meaning && <Help label={`What is ${label}?`}>{meaning}</Help>}
      </span>
      <span className="font-mono text-2xl font-medium tabular-nums">{children}</span>
      {note && <span className="text-muted-foreground text-xs">{note}</span>}
      <PartNote rule={r} />
    </>
  );
  const props = part ? partProps(part) : {};
  return href ? (
    <Link
      {...props}
      href={href}
      className="hover:bg-accent/40 focus-visible:ring-ring/50 flex flex-col gap-1 p-4 transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
    >
      {body}
    </Link>
  ) : (
    <div className="flex flex-col gap-1 p-4" {...props}>
      {body}
    </div>
  );
}
