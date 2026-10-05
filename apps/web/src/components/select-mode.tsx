"use client";

import { useQuery } from "@tanstack/react-query";
import { Crosshair } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { isSnapshot, pointAt, q, type Selection } from "@/lib/api";

// Whether the next click points the agent at a block instead of acting: one flag for the whole
// app, so the top bar and the command menu turn the same mode on.
let selecting = false;
const listeners = new Set<() => void>();
export function setSelecting(on: boolean) {
  selecting = on;
  document.documentElement.toggleAttribute("data-selecting", on);
  listeners.forEach((l) => l());
}
const useSelecting = () =>
  useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => selecting,
    () => false,
  );

/** Select mode can hand a block to the agent only on a server that launches. */
export function useCanPoint() {
  const health = useQuery(q.health());
  return health.data?.launching === true && !isSnapshot();
}

/** The block under the pointer: the innermost element with a data-ui id. */
const blockAt = (target: EventTarget | null) =>
  target instanceof Element ? target.closest<HTMLElement>("[data-ui]") : null;

/** A pointed-at block as text for any agent's prompt, with what it needs to find and change it. */
export function reference(s: Selection): string {
  const region = s.id.split("/")[0];
  return [
    `louped block ${s.id}`,
    `page: ${s.url}`,
    s.run && `run: ${s.run}`,
    s.experiment && `experiment: ${s.experiment}`,
    s.text && `shows: ${s.text.replace(/\s+/g, " ").slice(0, 200)}`,
    `region: ${region} (ui_page lists its blocks; set_layout changes them)`,
  ]
    .filter(Boolean)
    .join("\n");
}

/** Hands the block to the agent (ui_selection) and copies its reference, for an agent without
 * louped's tools or a prompt typed elsewhere. */
async function point(s: Selection) {
  try {
    await pointAt(s);
  } catch (err) {
    toast.error("Pointing failed", { description: (err as Error).message });
    return;
  }
  const copied = await navigator.clipboard?.writeText(reference(s)).then(
    () => true,
    () => false,
  );
  toast.success(`Your agent can see ${s.id}`, {
    description: copied
      ? "Its reference is copied too. Ask your agent to change it."
      : "Ask your agent to change it; it reads which with ui_selection.",
  });
}

/** The top bar's crosshair: point at any block (a card, a tab, a header) and the person's agent
 * reads which with ui_selection, so "make this smaller" needs no description. */
export function SelectButton() {
  const on = useSelecting();
  const canPoint = useCanPoint();

  useEffect(() => {
    if (!on) return;
    let marked: HTMLElement | null = null;
    const mark = (el: HTMLElement | null) => {
      marked?.removeAttribute("data-ui-hover");
      marked = el;
      marked?.setAttribute("data-ui-hover", "");
    };
    const onMove = (e: PointerEvent) => mark(blockAt(e.target));
    const onClick = (e: MouseEvent) => {
      const el = blockAt(e.target);
      if (!el || (e.target instanceof Element && e.target.closest("[data-select-control]"))) return;
      e.preventDefault();
      e.stopPropagation();
      const params = new URLSearchParams(location.search);
      const id = el.dataset.ui!;
      const onRun = location.pathname.startsWith("/run/");
      const onExperiment = location.pathname.includes("/experiment/");
      setSelecting(false);
      const picked = {
        id,
        url: location.pathname + location.search,
        run: onRun ? params.get("id") : null,
        experiment: onExperiment ? params.get("name") : null,
        text: el.innerText.trim().slice(0, 500),
      };
      void point(picked);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelecting(false);
    document.addEventListener("pointermove", onMove);
    document.addEventListener("click", onClick, true); // before the block's own click
    document.addEventListener("keydown", onKey);
    return () => {
      mark(null);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [on]);

  if (!canPoint) return null;
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className={on ? "bg-accent text-foreground" : undefined}
      data-select-control
      aria-pressed={on}
      aria-label="Point your agent at a block"
      title={
        on ? "Click a block to point your agent at it (Esc to stop)" : "Point your agent at a block"
      }
      onClick={() => setSelecting(!on)}
    >
      <Crosshair />
    </Button>
  );
}
