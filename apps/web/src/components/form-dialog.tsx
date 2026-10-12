"use client";

import { part, partId } from "@/components/parts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

/** A project's or an experiment's name: its folder, as louped.core.paths.NAME allows. */
export const NAME_PATTERN = "[a-z0-9][a-z0-9\\-]{0,63}";

/** A dialog's form, its fields as labels over inputs. */
export function FormDialog({
  open,
  onOpenChange,
  id,
  title,
  description,
  children,
  onSubmit,
  pending,
  submit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  id: string;
  title: string;
  description: string;
  children: React.ReactNode;
  onSubmit: (form: FormData) => void;
  pending: boolean;
  submit: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5" {...part(partId("projects/dialog", id))}>
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">{title}</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            {description}
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(new FormData(e.currentTarget));
          }}
        >
          {children}
          <Button type="submit" size="sm" className="self-end" disabled={pending}>
            {submit}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      {text}
      {children}
    </label>
  );
}

export const text = (form: FormData, key: string) => String(form.get(key) ?? "").trim();
