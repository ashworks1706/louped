"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const Sheet = DialogPrimitive.Root;
const SheetTitle = DialogPrimitive.Title;
const SheetDescription = DialogPrimitive.Description;
const SheetTrigger = DialogPrimitive.Trigger;

const SIDES = {
  right:
    "inset-y-0 right-0 border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-2xl",
  left: "inset-y-0 left-0 border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left",
};

/** A panel over the page: on the right for detail that belongs to a row (a transcript, a
 * sample), on the left for navigation on a phone. */
function SheetContent({
  className,
  children,
  side = "right",
  onInteractOutside,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { side?: keyof typeof SIDES }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/30" />
      <DialogPrimitive.Content
        className={cn(
          "bg-background data-[state=closed]:animate-out data-[state=open]:animate-in fixed z-50 flex w-full flex-col shadow-2xl duration-200",
          SIDES[side],
          className,
        )}
        // the picked parts' tray and an agent's note sit above a panel without closing it
        onInteractOutside={(e) => {
          const t = e.target;
          if (t instanceof Element && t.closest("[data-part-tray], [data-cue-note]"))
            e.preventDefault();
          else onInteractOutside?.(e);
        }}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          data-part="panel/close"
          className="text-muted-foreground hover:bg-accent hover:text-foreground absolute top-4 right-4 rounded-md p-1 transition-colors"
        >
          <X className="size-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger };
