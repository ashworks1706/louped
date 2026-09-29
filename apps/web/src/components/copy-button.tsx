"use client";

import { Check, Copy, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text); // unavailable over plain HTTP to another host
      setState("copied");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 1500);
  };
  const label = state === "failed" ? "Copy failed: select the text instead" : "Copy command";
  return (
    <Button variant="ghost" size="icon-sm" onClick={copy} aria-label={label} title={label}>
      {state === "copied" ? <Check /> : state === "failed" ? <X /> : <Copy />}
    </Button>
  );
}
