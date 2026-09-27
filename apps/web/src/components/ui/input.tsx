import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/30 h-8 w-full min-w-0 rounded-md border bg-transparent px-2.5 text-sm outline-none focus-visible:ring-[3px]",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
