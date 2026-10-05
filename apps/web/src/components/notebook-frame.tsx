"use client";

import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";

import { QueryState } from "@/components/query-state";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";

const HEIGHT = "h-[calc(100svh-16rem)] min-h-96 w-full rounded-xl border";

/** A notebook as Jupyter shows it: the page the API draws with nbconvert, in the app's theme, in
 * a frame that runs no scripts, since a notebook's outputs can carry any. Math shows as its TeX,
 * and an interactive output as the static copy the notebook saved, if any. version changes when
 * the file does (its size or hash), so a notebook still running is drawn again. */
export function NotebookFrame({
  url,
  version,
  title,
}: {
  url: string;
  version: string;
  title: string;
}) {
  const { resolvedTheme } = useTheme();
  const theme = resolvedTheme === "dark" ? "dark" : "light";
  const page = useQuery({
    queryKey: ["notebook-page", url, version, theme],
    queryFn: async ({ signal }) => {
      const res = await fetch(`${url}?theme=${theme}`, { signal });
      if (!res.ok) throw new ApiError(res.status, `${title}: ${res.status} ${res.statusText}`);
      return res.text();
    },
    enabled: resolvedTheme !== undefined,
  });
  if (resolvedTheme === undefined) return <Skeleton className={HEIGHT} />;
  return (
    <QueryState query={page}>
      {(html) => <iframe title={title} sandbox="" srcDoc={html} className={HEIGHT} />}
    </QueryState>
  );
}
