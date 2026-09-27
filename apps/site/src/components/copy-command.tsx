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
      className="group bg-fd-card text-fd-foreground hover:bg-fd-accent flex items-center gap-3 rounded-lg border px-4 py-2.5 font-mono text-sm transition-colors"
      aria-label={`Copy ${command}`}
    >
      <span className="text-fd-muted-foreground select-none">$</span>
      {command}
      {copied ? (
        <Check className="text-fd-muted-foreground size-4" />
      ) : (
        <Copy className="text-fd-muted-foreground group-hover:text-fd-foreground size-4" />
      )}
    </button>
  );
}
