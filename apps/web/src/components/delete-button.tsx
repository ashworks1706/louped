"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { q } from "@/lib/api";

/** Delete, asked once, on a server that launches: what goes and how to undo it, then back to
 * the list it was on. */
export function DeleteButton({
  what,
  name,
  undo,
  remove,
  then,
  disabled,
}: {
  /** experiment, run, job */
  what: string;
  name: string;
  /** Where it goes and how it comes back. */
  undo: string;
  remove: () => Promise<unknown>;
  /** The page to open after. */
  then: string;
  /** Why it cannot be deleted yet; the button is off while set. */
  disabled?: string;
}) {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const go = useMutation({
    mutationFn: remove,
    meta: { action: `Delete ${what}` },
    onSuccess: () => {
      setOpen(false);
      toast(`Deleted ${name}`, { description: undo });
      router.push(then);
      void client.invalidateQueries();
    },
  });
  if (!health.data?.launching) return null;
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={!!disabled}
        title={disabled ?? `Delete this ${what}`}
        aria-label={`Delete ${what}`}
      >
        <Trash2 />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-col gap-1">
            <DialogTitle className="text-sm font-medium">
              Delete {what} <span className="font-mono">{name}</span>?
            </DialogTitle>
            <DialogDescription className="text-muted-foreground text-xs">{undo}</DialogDescription>
          </div>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => go.mutate()} disabled={go.isPending}>
              Delete
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
