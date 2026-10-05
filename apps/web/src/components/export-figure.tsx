"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { NativeSelect } from "@/components/ui/native-select";
import { exportFigure, q } from "@/lib/api";
import { reportHref } from "@/lib/href";

const FORMATS = ["svg", "png", "pdf"] as const;

/** Exports a figure to reports/figures/ as SVG, PNG or PDF, with its ref and trace beside it,
 * for a deck or a document. Shown only on a server that launches. */
export function ExportFigure({ figure }: { figure: string }) {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const router = useRouter();
  const go = useMutation({
    mutationFn: (format: (typeof FORMATS)[number]) => exportFigure({ ref: figure, format }),
    meta: { action: "Export figure" },
    onSuccess: (made) => {
      void client.invalidateQueries({ queryKey: ["reports"] });
      toast(`Exported to reports/${made.path}`, {
        action: { label: "Open", onClick: () => router.push(reportHref(made.path)) },
      });
    },
  });
  if (!health.data?.launching) return null;
  return (
    <NativeSelect
      aria-label="Export figure"
      value=""
      disabled={go.isPending}
      onChange={(e) => go.mutate(e.target.value as (typeof FORMATS)[number])}
      className="h-7 text-xs"
    >
      <option value="" disabled>
        Export
      </option>
      {FORMATS.map((f) => (
        <option key={f} value={f}>
          {f.toUpperCase()}
        </option>
      ))}
    </NativeSelect>
  );
}
