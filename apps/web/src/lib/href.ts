/** The app's in-page links, built in one place. */

import type { Experiment } from "@/lib/api";

export const runHref = (id: string, tab?: string) =>
  `/run/?id=${encodeURIComponent(id)}${tab ? `&tab=${tab}` : ""}`;

/** A run's Items tab with one item open, in its item folder ("" for the top level). */
export const itemHref = (run: string, folder: string, item: string) =>
  `${runHref(run, "items")}&set=${encodeURIComponent(folder)}&item=${encodeURIComponent(item)}`;

/** A source's viewer, at a page. */
export const sourceHref = (key: string, page?: number) =>
  `/source/?key=${encodeURIComponent(key)}${page ? `&page=${page}` : ""}`;

export const reportHref = (path: string) => `/report/?path=${encodeURIComponent(path)}`;

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

/** A URL's host to show; the URL as it is when it does not parse. */
export function host(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
