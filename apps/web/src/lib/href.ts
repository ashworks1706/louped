/** The app's in-page links, built in one place. */

export const runHref = (id: string, tab?: string) =>
  `/run/?id=${encodeURIComponent(id)}${tab ? `&tab=${tab}` : ""}`;

export const compareHref = (a: string, b: string) =>
  `/compare/?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`;

export const featureHref = (run: string, feature: number) =>
  `/feature/?run=${encodeURIComponent(run)}&f=${feature}`;
