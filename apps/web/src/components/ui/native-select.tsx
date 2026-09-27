import { ChevronDownIcon } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/** shadcn/ui's NativeSelect: a styled <select>, for long option lists the keyboard can search. */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative w-fit">
      <select
        className={cn(
          "focus-visible:border-ring focus-visible:ring-ring/30 bg-background h-8 w-full min-w-0 appearance-none rounded-md border py-0 pr-8 pl-2.5 text-sm outline-none focus-visible:ring-[3px]",
          className,
        )}
        {...props}
      />
      <ChevronDownIcon
        aria-hidden="true"
        className="text-muted-foreground pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2"
      />
    </div>
  );
}

export { NativeSelect };
