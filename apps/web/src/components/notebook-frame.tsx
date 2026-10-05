"use client";

import { useQuery } from "@tanstack/react-query";

import { QueryState } from "@/components/query-state";
import { ApiError } from "@/lib/api";

/** A notebook as Jupyter shows it: the page the API draws with nbconvert, in a frame that runs
 * no scripts, since a notebook's outputs can carry any. Math shows as its TeX, and an
 * interactive output as the static copy the notebook saved, if any. */
export function NotebookFrame({ url, title }: { url: string; title: string }) {
  const page = useQuery({
    queryKey: ["notebook-page", url],
    queryFn: async ({ signal }) => {
      const res = await fetch(url, { signal });
      if (!res.ok) throw new ApiError(res.status, `${title}: ${res.status} ${res.statusText}`);
      return res.text();
    },
  });
  return (
    <QueryState query={page}>
      {(html) => (
        <iframe
          title={title}
          sandbox=""
          srcDoc={html}
          className="h-[80vh] w-full rounded-xl border bg-white"
        />
      )}
    </QueryState>
  );
}
