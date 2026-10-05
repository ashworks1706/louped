"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Markdown } from "@/components/markdown";
import { useCanPick } from "@/components/pick-parts";
import { cueSeen, cuesAfter, type Cue } from "@/lib/api";
import { cn } from "@/lib/utils";

const POLL_MS = 1000;
/** An app opened after a cue was queued shows it only if it is this recent. */
const FRESH_S = 30;
/** How long a cue waits for its parts to be drawn after opening its page. */
const FIND_MS = 8000;
/** Once one of a cue's parts is drawn, how long to wait for the rest. */
const SETTLE_MS = 800;
/** A cue with no note fades by itself after this; one with a note stays until dismissed. */
const FADE_MS = 6000;

const find = (id: string) => document.querySelector<HTMLElement>(`[data-part="${CSS.escape(id)}"]`);

/** What the person's agent shows them (ui_show): it opens a page, scrolls to parts and points at
 * them, with its note beside the first. The agent hears back which parts were not there. */
export function Cues() {
  const canShow = useCanPick();
  const router = useRouter();
  const last = useRef<number | null>(null);
  const [cue, setCue] = useState<{ cue: Cue; ids: string[] } | null>(null);
  // the cue being shown; a newer one takes over, the next poll (often empty) does not stop it
  const showing = useRef(0);

  const cues = useQuery({
    queryKey: ["ui", "show"],
    queryFn: () => cuesAfter(last.current ?? 0),
    refetchInterval: POLL_MS,
    enabled: canShow,
  });

  useEffect(() => {
    const got = cues.data;
    if (!got) return;
    const first = last.current === null;
    last.current = Math.max(last.current ?? 0, ...got.cues.map((c) => c.id));
    // the cue's age by the server's clock, which queued it
    const next = got.cues
      .filter((c) => c.status === "pending" && (!first || got.now - c.at < FRESH_S))
      .at(-1);
    if (!next) return;
    const before = showing.current;
    showing.current = next.id;
    // the one it takes over from never found its parts: its agent hears so
    if (before > 0 && before !== next.id) void cueSeen(before, [], true).catch(() => undefined);
    const stopped = () => showing.current !== next.id;
    void (async () => {
      const started = Date.now();
      const target = next.url ? new URL(next.url, location.origin) : null;
      if (target && target.origin !== location.origin) {
        await cueSeen(next.id, next.parts).catch(() => undefined);
        return;
      }
      // /run?id=x and /run/?id=x are one page
      const page = (path: string, search: string) => path.replace(/\/?$/, "/") + search;
      const here = () => page(location.pathname, location.search);
      const from = here();
      if (target && page(target.pathname, target.search) !== from) {
        router.push(target.pathname + target.search);
        // the old page's parts are not the new page's: look once the address has changed
        while (!stopped() && here() === from && Date.now() - started < FIND_MS)
          await new Promise((r) => setTimeout(r, 50));
      }
      // every part, or once one is there a moment for the rest, or give up
      let firstSeen: number | null = null;
      let found = next.parts.map(find);
      while (!stopped() && found.some((f) => !f) && Date.now() - started < FIND_MS) {
        if (found.some(Boolean)) firstSeen ??= Date.now();
        if (firstSeen !== null && Date.now() - firstSeen > SETTLE_MS) break;
        await new Promise((r) => setTimeout(r, 100));
        found = next.parts.map(find);
      }
      if (stopped()) return;
      const missing = next.parts.filter((_: string, i: number) => !found[i]);
      found.find(Boolean)?.scrollIntoView({ block: "center", behavior: "smooth" });
      setCue({ cue: next, ids: next.parts.filter((_: string, i: number) => !!found[i]) });
      showing.current = 0;
      await cueSeen(next.id, missing).catch(() => undefined);
    })();
  }, [cues.data, router]);
  useEffect(
    () => () => {
      showing.current = -1; // unmounted: whatever is looking stops
    },
    [],
  );

  useEffect(() => {
    if (!cue || cue.cue.text) return;
    const t = setTimeout(() => setCue(null), FADE_MS);
    return () => clearTimeout(t);
  }, [cue]);

  if (!cue) return null;
  return <Overlay key={cue.cue.id} cue={cue.cue} ids={cue.ids} close={() => setCue(null)} />;
}

/** The boxes of the parts a cue points at, found again every frame: they follow the page as it
 * scrolls, and a part drawn anew (a table refetched) is the same part. */
function useBoxes(ids: string[]) {
  const [boxes, setBoxes] = useState<DOMRect[]>([]);
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      setBoxes((was) => {
        const now = ids
          .map(find)
          .filter((el): el is HTMLElement => !!el)
          .map((el) => el.getBoundingClientRect());
        const same =
          was.length === now.length &&
          was.every(
            (b, i) =>
              b.x === now[i].x &&
              b.y === now[i].y &&
              b.width === now[i].width &&
              b.height === now[i].height,
          );
        return same ? was : now;
      });
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [ids]);
  return boxes;
}

const PAD = 6;

function Overlay({ cue, ids, close }: { cue: Cue; ids: string[]; close: () => void }) {
  const boxes = useBoxes(ids);
  const [arrived, setArrived] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setArrived(true), 50);
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  const first = boxes[0];
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-0 z-[60]">
      {boxes.map((b, i) => (
        <div
          key={i}
          data-cue-box
          className={cn(
            "absolute rounded-xl border-2 border-current transition-all duration-300",
            "text-foreground",
            cue.style === "spotlight" && i === 0 && "shadow-[0_0_0_9999px_rgb(0_0_0/0.45)]",
            cue.style !== "pointer" && "animate-pulse",
          )}
          style={{
            left: b.left - PAD,
            top: b.top - PAD,
            width: b.width + 2 * PAD,
            height: b.height + 2 * PAD,
          }}
        />
      ))}
      {cue.style === "pointer" && first && (
        <span
          aria-hidden
          className="bg-foreground ring-foreground/30 absolute size-3 rounded-full ring-8 transition-all duration-700 ease-out"
          style={
            arrived
              ? { left: first.left + first.width / 2 - 6, top: first.top + first.height / 2 - 6 }
              : { left: window.innerWidth - 40, top: window.innerHeight - 40 }
          }
        />
      )}
      {cue.text && (
        <div
          role="status"
          data-cue-note
          className="bg-popover text-popover-foreground pointer-events-auto absolute flex w-80 max-w-[calc(100vw-2rem)] gap-2 rounded-xl border p-3 text-sm shadow-lg"
          style={notePlace(first)}
        >
          <div className="min-w-0 flex-1 [&_p]:my-0">
            <Markdown noImages>{cue.text}</Markdown>
          </div>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={close}
            className="text-muted-foreground hover:text-foreground self-start rounded p-0.5"
          >
            <X className="size-4" />
          </button>
        </div>
      )}
    </div>
  );
}

/** The note below its part, or above when there is no room below, always on screen; in the
 * corner without a part. */
function notePlace(b: DOMRect | undefined): React.CSSProperties {
  if (!b) return { right: 16, bottom: 16 };
  const room = 160; // about a note's height
  const left = Math.max(16, Math.min(b.left, window.innerWidth - 336));
  const below = b.bottom + PAD + 8;
  const above = b.top - PAD - 8 - room;
  const top = below + room < window.innerHeight ? below : above > 16 ? above : 16;
  return { left, top: Math.min(Math.max(16, top), window.innerHeight - room - 16) };
}
