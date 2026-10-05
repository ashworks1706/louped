"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { part, partId } from "@/components/parts";
import { Button } from "@/components/ui/button";
import { ApiError, exportFigure, q } from "@/lib/api";
import { reportHref } from "@/lib/href";

const FORMATS = ["svg", "png", "pdf"] as const;
type Format = (typeof FORMATS)[number];

/** Buttons that export a figure to reports/figures/ as SVG, PNG or PDF, with its ref and trace
 * beside it, for a deck or a document. A file of the same name is replaced only when asked.
 * Shown only on a server that launches. */
export function ExportFigure({ figure }: { figure: string }) {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const router = useRouter();
  const go = useMutation({
    mutationFn: ({ format, replace }: { format: Format; replace: boolean }) =>
      exportFigure({ ref: figure, format, replace }),
    meta: { action: "Export figure", quiet: (e) => e instanceof ApiError && e.status === 409 },
    onSuccess: (made) => {
      void client.invalidateQueries({ queryKey: ["reports"] });
      toast(`Exported to reports/${made.path}`, {
        action: { label: "Open", onClick: () => router.push(reportHref(made.path)) },
      });
    },
    onError: (e, { format }) => {
      if (!(e instanceof ApiError && e.status === 409)) return;
      toast(e.message, {
        action: { label: "Replace", onClick: () => go.mutate({ format, replace: true }) },
      });
    },
  });
  if (!health.data?.launching) return null;
  const name = figure.split("/").pop() ?? figure;
  return (
    <span
      role="group"
      aria-label="Export figure"
      className="flex items-center gap-0.5"
      {...part(partId("figures/export", name))}
    >
      <span className="text-muted-foreground mr-1 text-xs">Export</span>
      {FORMATS.map((format) => (
        <Button
          key={format}
          size="sm"
          variant="ghost"
          className="h-7 px-2 font-mono text-xs"
          disabled={go.isPending}
          onClick={() => go.mutate({ format, replace: false })}
        >
          {format.toUpperCase()}
        </Button>
      ))}
    </span>
  );
}
