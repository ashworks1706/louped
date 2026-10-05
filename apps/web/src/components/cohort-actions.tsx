"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { saveCohort, type Picked } from "@/lib/api";
import { idsParam } from "@/lib/href";

/** Where a picked item row is from (its data, from the Items tab). */
type From = { run: string; experiment: string | null; folder: string; key: string };

const fromOf = (p: Picked): From | null => {
  const data = p.data as { from?: From } | null;
  return p.id.startsWith("items/row/") && data?.from ? data.from : null;
};

/** Picked item rows of one run, as a cohort: read the conditions on only them, or save them in
 * the experiment to run again on just them. */
export function CohortActions({ parts }: { parts: Picked[] }) {
  const rows = parts.filter((p) => fromOf(p));
  const from = rows.length ? fromOf(rows[0])! : null;
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  if (!from || rows.some((p) => fromOf(p)!.run !== from.run)) return null;
  const ids = [...new Set(rows.map((p) => decodeURIComponent(p.id.split("/")[2])))];

  const only = () => {
    const url = new URL(rows[0].url, location.origin);
    url.searchParams.set("tab", "items");
    url.searchParams.set("ids", idsParam(ids));
    url.searchParams.delete("item");
    url.searchParams.delete("cohort");
    router.push(url.pathname + url.search);
  };
  return (
    <>
      <Button variant="ghost" size="sm" onClick={only} title="Read every condition on these items">
        Only these
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setSaving(true)}
        disabled={!from.experiment}
        title={
          from.experiment
            ? `Save as a cohort of ${from.experiment}, to run again on just these`
            : "This run has no experiment to save a cohort in"
        }
      >
        Save cohort
      </Button>
      {from.experiment && (
        <SaveCohort
          open={saving}
          onOpenChange={setSaving}
          experiment={from.experiment}
          from={from}
          ids={ids}
        />
      )}
    </>
  );
}

function SaveCohort({
  open,
  onOpenChange,
  experiment,
  from,
  ids,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  experiment: string;
  from: From;
  ids: string[];
}) {
  const client = useQueryClient();
  const router = useRouter();
  const save = useMutation({
    mutationFn: ({ name, note }: { name: string; note: string }) =>
      saveCohort(experiment, name, {
        ids,
        note,
        run: from.run,
        folder: from.folder,
        key: from.key,
      }),
    meta: { action: "Save cohort" },
    onSuccess: (saved) => {
      void client.invalidateQueries({ queryKey: ["cohorts", experiment] });
      onOpenChange(false);
      const launch = `/launch/?id=${encodeURIComponent(`script:${experiment}/run.py`)}&cohort=${saved.name}`;
      toast(`Saved cohort ${saved.name}`, {
        description: `experiments/${experiment}/cohorts/${saved.name}.json, to commit with the experiment`,
        action: { label: "Run on it", onClick: () => router.push(launch) },
      });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">
            Save {ids.length} {ids.length === 1 ? "item" : "items"} as a cohort
          </DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Saved in {experiment}; its run.py runs on just these with --cohort.
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            save.mutate({
              name: String(form.get("name") ?? ""),
              note: String(form.get("note") ?? ""),
            });
          }}
        >
          <label className="flex flex-col gap-1 text-xs">
            Name
            <Input
              name="name"
              required
              pattern="[a-z0-9][a-z0-9\-]{0,63}"
              title="Lowercase letters, digits and -"
              placeholder="flipped-under-pushback"
              className="font-mono placeholder:font-sans"
              autoComplete="off"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            What they have in common
            <Textarea name="note" rows={3} className="text-sm" />
          </label>
          <Button type="submit" size="sm" className="self-end" disabled={save.isPending}>
            Save
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
