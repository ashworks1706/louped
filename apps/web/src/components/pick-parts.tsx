"use client";

import { useQuery } from "@tanstack/react-query";
import { Copy, X } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { CohortActions } from "@/components/cohort-actions";
import { partData } from "@/components/parts";
import { Button } from "@/components/ui/button";
import { isSnapshot, pick, q, type Picked } from "@/lib/api";

// What the person has picked, in order: one list for the whole app, kept across pages, so they
// can pick a row here and a figure there and ask about both.
let picked: Picked[] = [];
let tapping = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => (listeners.add(l), () => listeners.delete(l));
const usePicked = () =>
  useSyncExternalStore(
    subscribe,
    () => picked,
    () => [] as Picked[],
  );
const useTapping = () =>
  useSyncExternalStore(
    subscribe,
    () => tapping,
    () => false,
  );

// the server's version of the list last sent; the agent has read it once the server's read is
// at least this
let sent = 0;
let syncing: ReturnType<typeof setTimeout> | undefined;
function setPicked(next: Picked[]) {
  picked = next;
  sent = 0;
  emit();
  // the agent reads the list as it stands; a burst of clicks sends once
  clearTimeout(syncing);
  syncing = setTimeout(() => {
    pick({ parts: picked })
      .then((p) => {
        sent = p.version;
        emit();
      })
      .catch((err: Error) =>
        toast.error("Your agent cannot see what you picked", { description: err.message }),
      );
  }, 150);
}
const useSent = () =>
  useSyncExternalStore(
    subscribe,
    () => sent,
    () => 0,
  );

/** Touch screens have no Shift: this turns taps into picks until Done. */
export function setTapping(on: boolean) {
  tapping = on;
  document.documentElement.toggleAttribute("data-picking", on);
  emit();
}

/** Picking hands parts to the agent, so only on a server that launches. */
export function useCanPick() {
  const health = useQuery(q.health());
  return health.data?.launching === true && !isSnapshot();
}

const partAt = (target: EventTarget | null) =>
  target instanceof Element ? target.closest<HTMLElement>("[data-part]") : null;

function read(el: HTMLElement): Picked {
  const params = new URLSearchParams(location.search);
  const id = el.dataset.part!;
  return {
    id,
    url: location.pathname + location.search,
    run: location.pathname.startsWith("/run/") ? params.get("id") : null,
    experiment: location.pathname.includes("/experiment/") ? params.get("name") : null,
    text: el.innerText.replace(/\s+/g, " ").trim().slice(0, 500),
    data: partData(id) as Picked["data"],
  };
}

/** The picked parts as text for any agent's prompt, numbered as the tray numbers them: what each
 * is, where, and its data. */
export function reference(parts: Picked[]): string {
  return parts
    .map((p, i) =>
      [
        `pick ${i + 1}: louped part ${p.id}`,
        `page: ${p.url}`,
        p.run && `run: ${p.run}`,
        p.experiment && `experiment: ${p.experiment}`,
        p.text && `shows: ${p.text.slice(0, 200)}`,
        p.data != null && `data: ${JSON.stringify(p.data).slice(0, 2000)}`,
      ]
        .filter(Boolean)
        .join("\n"),
    )
    .join("\n\n");
}

const esc = (id: string) => CSS.escape(id);

/** Shift+click any part (a card, a row, a field, a control) to pick it, again to drop it; the
 * agent reads the picks with ui_selection, or with the person's next message through louped's
 * prompt hook. A tray numbers them (@sel 2 names the second), says whether the agent has read
 * them, and copies them for an agent without louped's tools. */
export function PartPicker() {
  const canPick = useCanPick();
  const parts = usePicked();
  const tap = useTapping();
  const version = useSent();
  const server = useQuery({ ...q.picks(), enabled: canPick && parts.length > 0 });
  const agentRead = version > 0 && (server.data?.read ?? 0) >= version;
  const query = useSearchParams().toString();
  const here = usePathname() + (query ? `?${query}` : "");

  useEffect(() => {
    if (!canPick) return;
    const root = document.documentElement;
    let marked: HTMLElement | null = null;
    const mark = (el: HTMLElement | null) => {
      marked?.removeAttribute("data-part-hover");
      marked = el;
      marked?.setAttribute("data-part-hover", "");
    };
    const picking = (e: MouseEvent | KeyboardEvent) => e.shiftKey || tapping;
    const onKey = (e: KeyboardEvent) => {
      root.toggleAttribute("data-shift", e.shiftKey);
      if (!e.shiftKey && !tapping) mark(null);
      // Escape closes a panel or an agent's note first; with neither open it clears the picks
      const open = document.querySelector("[role=dialog], [data-cue-note]");
      if (e.type === "keydown" && e.key === "Escape" && !open && (picked.length || tapping)) {
        setTapping(false);
        setPicked([]);
      }
    };
    const onBlur = () => {
      root.removeAttribute("data-shift");
      mark(null);
    };
    const onMove = (e: PointerEvent) => mark(picking(e) ? partAt(e.target) : null);
    // Shift+mousedown would start a text selection; a pick is not one
    const onDown = (e: MouseEvent) => {
      if (picking(e) && partAt(e.target) && !inTray(e.target)) e.preventDefault();
    };
    const onClick = (e: MouseEvent) => {
      const el = partAt(e.target);
      if (!el || !picking(e) || inTray(e.target)) return;
      e.preventDefault();
      e.stopPropagation(); // before the part's own click: a pick opens nothing
      const id = el.dataset.part!;
      const url = location.pathname + location.search;
      const at = picked.findIndex((p) => p.id === id && p.url === url);
      setPicked(at >= 0 ? picked.filter((_, i) => i !== at) : [...picked, read(el)]);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("keyup", onKey);
    window.addEventListener("blur", onBlur);
    document.addEventListener("pointermove", onMove);
    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("click", onClick, true);
    return () => {
      onBlur();
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("keyup", onKey);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("mousedown", onDown, true);
      document.removeEventListener("click", onClick, true);
    };
  }, [canPick]);

  if (!canPick) return null;
  const outlined = parts
    .filter((p) => p.url === here)
    .map((p) => `[data-part="${esc(p.id)}"]`)
    .join(",");
  if (parts.length === 0 && !tap) return null;
  return (
    <>
      {outlined && (
        <style>{`${outlined} { outline: 2px solid var(--foreground); outline-offset: 2px; }`}</style>
      )}
      <div
        data-part-tray
        role="region"
        aria-label="Picked parts"
        className="bg-popover text-popover-foreground pointer-events-auto fixed bottom-4 left-1/2 z-[60] flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-2 rounded-xl border px-3 py-2 text-xs shadow-lg"
      >
        <span className="text-muted-foreground shrink-0">
          {parts.length
            ? `${parts.length} picked · ${agentRead ? "your agent has read them" : "not read by your agent yet"}`
            : "Tap parts to pick them"}
        </span>
        <ul className="flex min-w-0 gap-1 overflow-x-auto">
          {parts.map((p, i) => (
            <li
              key={`${p.url} ${p.id}`}
              className="bg-muted flex shrink-0 items-center gap-1 rounded-md py-0.5 pr-0.5 pl-2 font-mono"
              title={`pick ${i + 1}: ${p.id}\n${p.url}`}
            >
              <span className="text-muted-foreground">{i + 1}</span>
              {shortName(p.id)}
              <button
                type="button"
                aria-label={`Drop ${p.id}`}
                className="hover:bg-accent rounded p-0.5"
                onClick={() => setPicked(picked.filter((_, j) => j !== i))}
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
        <CohortActions parts={parts} />
        {parts.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              void navigator.clipboard
                ?.writeText(reference(picked))
                .then(() => toast.success("Copied, to paste into any agent"))
            }
          >
            <Copy /> Copy
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setTapping(false);
            setPicked([]);
          }}
        >
          {tap && parts.length === 0 ? "Done" : "Clear"}
        </Button>
      </div>
    </>
  );
}

const inTray = (t: EventTarget | null) => t instanceof Element && !!t.closest("[data-part-tray]");

/** A part's name for the tray: its last two segments, decoded. */
const shortName = (id: string) => id.split("/").slice(-2).map(decodeURIComponent).join(" / ");
