"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, StickyNote, Trash2, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { part, partId } from "@/components/parts";
import { useCanPick } from "@/components/pick-parts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { addNote, deleteNote, editNote, q, type Anchor, type Note } from "@/lib/api";
import { ago } from "@/lib/format";
import { cn } from "@/lib/utils";

const find = (id: string) => document.querySelector<HTMLElement>(`[data-part="${CSS.escape(id)}"]`);

/** A part's name for a person: its last two segments, decoded. */
export const shortName = (id: string) =>
  id.split("/").slice(-2).map(decodeURIComponent).join(" / ");

/** /run?id=x and /run/?id=x are one page. */
const path = (url: string) => new URL(url, "http://x").pathname.replace(/\/?$/, "/");

/** Whether an anchor is on the page open now: the same page, showing the same run or experiment.
 * The router's path, not location's: the address changes after the new page draws. */
function onPage(a: Anchor, pathname: string, here: URLSearchParams) {
  if (path(a.url) !== path(pathname)) return false;
  if (a.run && a.run !== here.get("id")) return false;
  if (a.experiment && a.experiment !== here.get("name")) return false;
  return true;
}

/** Where an anchor's page opens with its note shown. */
export function noteHref(a: Anchor, id: string) {
  const url = new URL(a.url, "http://x");
  url.searchParams.set("note", id);
  return url.pathname + url.search;
}

/** Writes a note on parts: the picks in the tray, or the points of a figure's lasso. */
export function NoteDialog({
  anchors,
  open,
  onOpenChange,
  onSaved,
}: {
  anchors: Anchor[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (note: Note) => void;
}) {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const save = useMutation({
    mutationFn: () => addNote({ text, anchors, by: "person" }),
    meta: { action: "Keep note" },
    onSuccess: (note) => {
      client.setQueryData<Note[]>(["notes"], (was) => [note, ...(was ?? [])]);
      void client.invalidateQueries({ queryKey: ["notes"] });
      setText("");
      onOpenChange(false);
      toast("Note kept", { description: "On the part, and on Notes." });
      onSaved?.(note);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-3 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">
            Note on {anchors.length === 1 ? shortName(anchors[0].part) : `${anchors.length} parts`}
          </DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Kept in the project&apos;s notes/ folder, with what the parts show now. Your agent reads
            it with notes.
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) save.mutate();
          }}
        >
          <Textarea
            aria-label="Note"
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim()) save.mutate();
            }}
            placeholder="What you see here. Markdown."
            className="min-h-28 text-sm"
          />
          <Button
            type="submit"
            size="sm"
            className="self-end"
            disabled={!text.trim() || save.isPending}
          >
            Keep note
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** One note: what it says, who wrote it and when, and, on the Notes page, the parts it is on.
 * Where the app launches, it can be edited, and deleted to the trash after one confirm. */
export function NoteCard({ note, links }: { note: Note; links?: boolean }) {
  const canEdit = useCanPick();
  const client = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const save = useMutation({
    mutationFn: (text: string) => editNote(note.id, text),
    meta: { action: "Edit note" },
    onSuccess: (got) => {
      client.setQueryData<Note[]>(["notes"], (was) => was?.map((n) => (n.id === got.id ? got : n)));
      setEditing(null);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteNote(note.id),
    meta: { action: "Delete note" },
    onSuccess: () => {
      client.setQueryData<Note[]>(["notes"], (was) => was?.filter((n) => n.id !== note.id));
      toast("Note deleted", { description: "It is in .louped/trash/notes." });
    },
  });
  const id = (what: string) => partId(`notes/${what}`, note.id);
  return (
    <article className="flex flex-col gap-2 text-sm" {...part(id("note"))}>
      {editing === null ? (
        <div className="min-w-0 [&_p]:my-0">
          <Markdown noImages>{note.text}</Markdown>
        </div>
      ) : (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (editing.trim()) save.mutate(editing);
          }}
        >
          <Textarea
            aria-label="Note"
            autoFocus
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
            className="min-h-24 text-sm"
            {...part(id("text"))}
          />
          <span className="flex justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setEditing(null)}
              {...part(id("cancel"))}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={!editing.trim() || save.isPending}
              {...part(id("save"))}
            >
              Save
            </Button>
          </span>
        </form>
      )}
      <footer className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span>
          {note.by === "agent" ? "Your agent" : "You"} · {ago(note.updated)}
        </span>
        {links &&
          note.anchors.map((a, i) => (
            <Link
              key={i}
              href={noteHref(a, note.id)}
              className="hover:text-foreground font-mono underline-offset-2 hover:underline"
              title={`${a.part}\n${a.url}${a.shows ? `\n${a.shows}` : ""}`}
              {...part(partId("notes/anchor", note.id, i))}
            >
              {shortName(a.part)}
              {a.run && ` · ${a.run}`}
              {a.experiment && ` · ${a.experiment}`}
            </Link>
          ))}
        {canEdit && editing === null && (
          <span className="ml-auto flex items-center">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Edit note"
              onClick={() => setEditing(note.text)}
              {...part(id("edit"))}
            >
              <Pencil className="size-3" />
            </Button>
            {confirm ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-negative h-6 px-2 text-xs"
                onClick={() => remove.mutate()}
                onBlur={() => setConfirm(false)}
                autoFocus
                disabled={remove.isPending}
                {...part(id("delete"))}
              >
                <Check className="size-3" /> Delete
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Delete note"
                onClick={() => setConfirm(true)}
                {...part(id("delete"))}
              >
                <Trash2 className="size-3" />
              </Button>
            )}
          </span>
        )}
      </footer>
    </article>
  );
}

type Mark = { part: string; notes: Note[]; box: DOMRect };

/** The notes on the page open now, as a mark at the corner of each part they are on; a mark
 * opens its notes. ?note=<id> opens that note's mark, as the Notes page links. The marks follow
 * the page as it scrolls and a part drawn anew. */
export function NoteMarks() {
  const notes = useQuery(q.notes());
  const params = useSearchParams();
  const pathname = usePathname();
  const asked = params.get("note");
  // the part whose notes are open; undefined follows ?note=
  const [picked, setOpen] = useState<string | null | undefined>(undefined);
  const [drawn, setMarks] = useState<Mark[]>([]);
  // each part on this page that has notes, with them
  const here = useMemo(() => {
    const by = new Map<string, Note[]>();
    for (const n of notes.data ?? [])
      for (const a of n.anchors)
        if (onPage(a, pathname, params) && !by.get(a.part)?.includes(n))
          by.set(a.part, [...(by.get(a.part) ?? []), n]);
    return by;
  }, [notes.data, pathname, params]);

  const marks = here.size ? drawn : [];

  useEffect(() => {
    if (here.size === 0) return;
    let frame = 0;
    const tick = () => {
      const now: Mark[] = [];
      for (const [id, list] of here) {
        const box = find(id)?.getBoundingClientRect();
        if (box && box.width > 0) now.push({ part: id, notes: list, box });
      }
      setMarks((was) =>
        was.length === now.length &&
        was.every(
          (m, i) => m.part === now[i].part && same(m.box, now[i].box) && m.notes === now[i].notes,
        )
          ? was
          : now,
      );
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [here]);

  // a link to a note opens it once its part is drawn, and scrolls to it
  const askedPart = asked ? marks.find((m) => m.notes.some((n) => n.id === asked))?.part : null;
  const open = picked === undefined ? (askedPart ?? null) : picked;
  useEffect(() => {
    if (askedPart) find(askedPart)?.scrollIntoView({ block: "center" });
  }, [askedPart]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const shown = marks.find((m) => m.part === open);
  if (marks.length === 0) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-30" data-note-marks>
      {marks.map((m) => (
        <button
          key={m.part}
          type="button"
          aria-label={`${m.notes.length} note${m.notes.length > 1 ? "s" : ""} on ${shortName(m.part)}`}
          aria-expanded={open === m.part}
          onClick={() => setOpen(open === m.part ? null : m.part)}
          className={cn(
            "bg-foreground text-background pointer-events-auto absolute flex h-5 min-w-5 items-center justify-center gap-0.5 rounded-full px-1 text-[10px] font-medium shadow-sm",
            open === m.part && "ring-foreground/30 ring-4",
          )}
          style={{ left: Math.min(m.box.right - 10, window.innerWidth - 28), top: m.box.top - 8 }}
          {...part(partId("notes/mark", m.notes[0].id))}
        >
          <StickyNote className="size-3" />
          {m.notes.length > 1 && m.notes.length}
        </button>
      ))}
      {shown && (
        <div
          role="dialog"
          aria-label={`Notes on ${shortName(shown.part)}`}
          className="bg-popover text-popover-foreground pointer-events-auto absolute flex max-h-[60vh] w-80 max-w-[calc(100vw-2rem)] flex-col gap-3 overflow-y-auto rounded-xl border p-3 shadow-lg"
          style={place(shown.box)}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground font-mono text-xs">{shortName(shown.part)}</span>
            <button
              type="button"
              aria-label="Close notes"
              onClick={() => setOpen(null)}
              className="text-muted-foreground hover:text-foreground rounded p-0.5"
              {...part(partId("notes/close", shown.notes[0].id))}
            >
              <X className="size-4" />
            </button>
          </div>
          {shown.notes.map((n) => (
            <NoteCard key={n.id} note={n} />
          ))}
        </div>
      )}
    </div>
  );
}

const same = (a: DOMRect, b: DOMRect) =>
  a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;

/** The notes beside their mark: below it, or above when there is no room, always on screen. */
function place(b: DOMRect): React.CSSProperties {
  const room = 200;
  const left = Math.max(16, Math.min(b.right - 320, window.innerWidth - 336));
  const below = b.top + 16;
  const top = below + room < window.innerHeight ? below : Math.max(16, b.top - room - 8);
  return { left, top };
}
