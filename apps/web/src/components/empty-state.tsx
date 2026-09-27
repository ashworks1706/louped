import type { LucideIcon } from "lucide-react";

import { CopyButton } from "@/components/copy-button";

/** What a page shows before it has data: what will be here, and the command that fills it. */
export function EmptyState({
  icon: Icon,
  title,
  body,
  command,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  command: string;
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed px-6 py-16 text-center">
      <div className="bg-muted grid size-10 place-items-center rounded-lg border">
        <Icon className="text-muted-foreground size-5" />
      </div>
      <h2 className="mt-4 font-medium">{title}</h2>
      <p className="text-muted-foreground mt-1 max-w-sm text-sm">{body}</p>
      <div className="bg-muted/50 mt-6 flex w-full max-w-md items-center gap-2 rounded-lg border py-1 pr-1 pl-3 text-left">
        <code className="flex-1 truncate font-mono text-[13px]">
          <span className="text-muted-foreground select-none">$ </span>
          {command}
        </code>
        <CopyButton text={command} />
      </div>
    </div>
  );
}
