"use client";

import { CircleHelp } from "lucide-react";
import { useState } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** A ? that explains what it sits beside: on hover, focus or tap. */
export function Help({ children, label = "What is this?" }: { children: string; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Tooltip open={open} onOpenChange={setOpen} delayDuration={150}>
      <TooltipTrigger
        aria-label={label}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-grid size-4 shrink-0 place-items-center rounded-full align-middle outline-none focus-visible:ring-2"
        // Radix closes a tooltip on press and never opens one on touch; a tap opens it instead,
        // and a tap anywhere else or Escape closes it.
        onPointerDown={(e) => e.preventDefault()}
        onClick={(e) => {
          // Inside a clickable row, a tap reads the help instead of opening the row.
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <CircleHelp className="size-3.5" />
      </TooltipTrigger>
      <TooltipContent>{children}</TooltipContent>
    </Tooltip>
  );
}
