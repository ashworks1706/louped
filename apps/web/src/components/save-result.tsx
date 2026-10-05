"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { part, useRules } from "@/components/parts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/native-select";
import { q, saveResult, type View } from "@/lib/api";
import { runHref } from "@/lib/href";

type Tool = "reply" | "inspect" | "patch" | "dose" | "speed";
/** What one tool showed: its figures, the prompt and the request it sent. */
export type Result = {
  prompt: string;
  settings: Record<string, unknown>;
  label: string;
  views: View[];
};

/** Keep what a Probe or Benchmark tool showed as a run, under one of the experiments or the
 * tool's own (probe, benchmark), so a finding made by hand lands beside the experiments' runs. */
export function SaveResult({ tool, result }: { tool: Tool; result: Result | null }) {
  const [open, setOpen] = useState(false);
  if (useRules()("playground/save").hidden) return null;
  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        disabled={!result}
        onClick={() => setOpen(true)}
        title={result ? "Keep this result as a run" : "Run the tool first"}
        {...part("playground/save")}
      >
        <Save /> Save as run
      </Button>
      {result && <Saving open={open} onOpenChange={setOpen} tool={tool} result={result} />}
    </>
  );
}

function Saving({
  open,
  onOpenChange,
  tool,
  result,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tool: Tool;
  result: Result;
}) {
  const own = tool === "speed" ? "benchmark" : "probe";
  const experiments = useQuery(q.experiments());
  const [experiment, setExperiment] = useState("");
  const client = useQueryClient();
  const router = useRouter();
  const save = useMutation({
    mutationFn: () =>
      saveResult({
        tool,
        ...result,
        settings: result.settings as Record<string, never>,
        experiment: experiment || null,
      }),
    meta: { action: "Save as run" },
    onSuccess: ({ run }) => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      onOpenChange(false);
      toast(`Saved under ${experiment || own}`, {
        description: `${result.views.length} ${result.views.length === 1 ? "figure" : "figures"}, the prompt and its settings`,
        action: { label: "Open", onClick: () => router.push(runHref(run)) },
      });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">Save as a run</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            {result.views.length} {result.views.length === 1 ? "figure" : "figures"} from {tool},
            with the prompt and the settings sent.
          </DialogDescription>
        </div>
        <label className="flex flex-col gap-1 text-xs">
          Under
          <NativeSelect
            aria-label="Experiment"
            value={experiment}
            onChange={(e) => setExperiment(e.target.value)}
            className="w-full font-mono text-xs"
          >
            <option value="">{own} (no question)</option>
            {(experiments.data ?? []).map((e) => (
              <option key={e.name} value={e.name}>
                {e.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <Button
          size="sm"
          className="self-end"
          disabled={save.isPending}
          onClick={() => save.mutate()}
        >
          Save
        </Button>
      </DialogContent>
    </Dialog>
  );
}
