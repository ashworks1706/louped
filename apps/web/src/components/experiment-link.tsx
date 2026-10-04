"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { q } from "@/lib/api";
import { experimentHref } from "@/lib/href";

/** An experiment's name, linked to its page under its domain; plain text when no folder has
 * that name (runs written under a name with no README, such as the examples). */
export function ExperimentLink({ name, className }: { name: string; className?: string }) {
  const experiments = useQuery(q.experiments());
  const found = experiments.data?.find((e) => e.name === name);
  if (!found) return <span className={className}>{name}</span>;
  return (
    <Link
      href={experimentHref(name, found.axis)}
      className={`${className ?? ""} hover:underline`}
      onClick={(e) => e.stopPropagation()}
    >
      {name}
    </Link>
  );
}
