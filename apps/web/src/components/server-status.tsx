"use client";

import { useEffect, useState } from "react";

import { health, type Health } from "@/lib/api";
import { cn } from "@/lib/utils";

type State = { kind: "checking" } | { kind: "up"; health: Health } | { kind: "down" };

/** Whether the API answers. Checked on load and every 15 seconds. */
export function ServerStatus() {
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    const check = () =>
      health(controller.signal)
        .then((h) => setState({ kind: "up", health: h }))
        .catch(() => !controller.signal.aborted && setState({ kind: "down" }));
    check();
    const timer = setInterval(check, 15_000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  const label =
    state.kind === "up"
      ? `API v${state.health.version}`
      : state.kind === "down"
        ? "API offline"
        : "Connecting";

  return (
    <div className="text-muted-foreground flex items-center gap-2 text-xs" title={label}>
      <span
        className={cn(
          "size-1.5 rounded-full",
          state.kind === "up" && "bg-positive",
          state.kind === "down" && "bg-negative",
          state.kind === "checking" && "bg-muted-foreground/50",
        )}
      />
      <span className="font-mono">{label}</span>
    </div>
  );
}
