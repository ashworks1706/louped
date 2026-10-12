"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { Fragment } from "react";

import { part, partId } from "@/components/parts";
import { q } from "@/lib/api";
import { experimentHref, projectHref } from "@/lib/href";

export type Crumb = { key: string; label: string; href?: string };

/** Where a page sits: project, experiment, run. Each step links up; the last is this page. */
export function Crumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" {...part("crumbs")}>
      <ol className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-1 text-xs">
        {items.map((c, i) => (
          <Fragment key={c.key}>
            {i > 0 && <ChevronRight className="size-3 shrink-0" aria-hidden />}
            <li className="min-w-0 truncate" {...part(partId("crumbs/step", c.key))}>
              {c.href && i < items.length - 1 ? (
                <Link
                  href={c.href}
                  className="hover:text-foreground underline-offset-4 hover:underline"
                >
                  {c.label}
                </Link>
              ) : (
                <span aria-current={i === items.length - 1 ? "page" : undefined}>{c.label}</span>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}

/** The steps above an experiment: its project when it has one, else every experiment. */
export function useTrail(experiment: string | null | undefined): Crumb[] {
  const experiments = useQuery({ ...q.experiments(), enabled: !!experiment });
  const projects = useQuery(q.projects());
  const project = experiment
    ? experiments.data?.find((e) => e.name === experiment)?.project
    : undefined;
  const title = projects.data?.find((p) => p.name === project)?.title ?? project;
  return [
    project
      ? { key: "project", label: title ?? project, href: projectHref(project) }
      : { key: "experiments", label: "Experiments", href: "/experiments/" },
    ...(experiment
      ? [
          {
            key: "experiment",
            label: experiment,
            href: experimentHref(experiment),
          },
        ]
      : []),
  ];
}
