import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { CopyButton } from "@/components/copy-button";
import { Button } from "@/components/ui/button";

/** What a page shows before it has data: what will be here, and what fills it. That is a link
 * or a button into the app, or a command only where the app cannot do it, such as starting the
 * server or writing an experiment's files. */
export function EmptyState({
  icon: Icon,
  title,
  body,
  ...fill
}: {
  icon: LucideIcon;
  title: string;
  body?: string;
} & (
  | { action: { href: string; label: string } }
  | { command: string }
  | { children: React.ReactNode }
)) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed px-6 py-16 text-center">
      <div className="bg-muted grid size-10 place-items-center rounded-lg border">
        <Icon className="text-muted-foreground size-5" />
      </div>
      <h2 className="mt-4 font-medium">{title}</h2>
      {body && <p className="text-muted-foreground mt-1 max-w-sm text-sm">{body}</p>}
      {"children" in fill ? (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">{fill.children}</div>
      ) : "action" in fill ? (
        <Button asChild size="sm" className="mt-6">
          <Link href={fill.action.href}>{fill.action.label}</Link>
        </Button>
      ) : (
        <div className="bg-muted/50 mt-6 flex w-full max-w-md items-center gap-2 rounded-lg border py-1 pr-1 pl-3 text-left">
          <code className="flex-1 truncate font-mono text-[13px]">
            <span className="text-muted-foreground select-none">$ </span>
            {fill.command}
          </code>
          <CopyButton text={fill.command} />
        </div>
      )}
    </div>
  );
}
