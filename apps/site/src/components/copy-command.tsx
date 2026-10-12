"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

/** A shell command with a copy button. */
export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(command);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="group bg-fd-card text-fd-foreground hover:bg-fd-accent flex max-w-full items-center gap-3 rounded-lg border px-4 py-2.5 text-left font-mono text-sm transition-colors"
      aria-label={`Copy ${command}`}
    >
      <span className="text-fd-muted-foreground self-start select-none">$</span>
      <span className="min-w-0 break-all">{command}</span>
      {copied ? (
        <Check className="text-fd-muted-foreground size-4 shrink-0" />
      ) : (
        <Copy className="text-fd-muted-foreground group-hover:text-fd-foreground size-4 shrink-0" />
      )}
    </button>
  );
}
