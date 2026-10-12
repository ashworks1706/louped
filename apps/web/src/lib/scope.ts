import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";

import { AXES, type Axis } from "@/lib/nav";

/** The project the app is scoped to (?project=), or null for every project. The sidebar carries
 * it on each link, so moving between pages keeps the scope. */
export function useProject() {
  return useQueryState("project", parseAsString);
}

/** Behavior, efficiency, or both (null): the axis filter on lists (?axis=). */
export function useAxis() {
  return useQueryState("axis", parseAsStringLiteral(AXES.map((a) => a.axis)));
}

/** A page's address in the current project's scope. */
export function scoped(href: string, project: string | null): string {
  if (!project) return href;
  return `${href}${href.includes("?") ? "&" : "?"}project=${encodeURIComponent(project)}`;
}

export type { Axis };
