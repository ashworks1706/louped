/** The app's in-page links, built in one place. */

import type { Experiment } from "@/lib/api";

export const runHref = (id: string, tab?: string) =>
  `/run/?id=${encodeURIComponent(id)}${tab ? `&tab=${tab}` : ""}`;

export const jobHref = (id: string) => `/job/?id=${encodeURIComponent(id)}`;

/** The pages a domain's experiments live under; the checks file under behavior's. */
export const axisPath = (axis: Experiment["axis"]) =>
  axis === "efficiency" ? "/efficiency" : "/behavior";

export const experimentHref = (name: string, axis: Experiment["axis"], tab?: string) =>
  `${axisPath(axis)}/experiment/?name=${encodeURIComponent(name)}${tab ? `&tab=${tab}` : ""}`;

export const compareHref = (a: string, b: string) =>
  `/compare/?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`;

export const featureHref = (run: string, feature: number) =>
  `/behavior/feature/?run=${encodeURIComponent(run)}&f=${feature}`;

/** A cohort's ids in the URL: comma-separated, each URL-encoded. */
export const idsParam = (ids: string[]) => ids.map(encodeURIComponent).join(",");
