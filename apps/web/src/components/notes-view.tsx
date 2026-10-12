"use client";

import { useQuery } from "@tanstack/react-query";
import { StickyNote } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { useEffect } from "react";

import { EmptyState } from "@/components/empty-state";
import { NoteCard } from "@/components/notes";
import { QueryState } from "@/components/query-state";
import { q } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Every note kept on the project's parts, newest first, each linking to the parts it is on;
 * ?id= marks one, as add_note links it. */
export function NotesView() {
  const notes = useQuery(q.notes());
  const [id] = useQueryState("id", parseAsString);
  useEffect(() => {
    if (id && notes.data?.some((n) => n.id === id))
      document.getElementById(`note-${id}`)?.scrollIntoView({ block: "center" });
  }, [id, notes.data]);
  return (
    <QueryState query={notes}>
      {(all) =>
        all.length === 0 ? (
          <EmptyState
            icon={StickyNote}
            title="No notes yet"
            body="Shift+click any part of a page, a row, a figure, a field, then press Note in the tray. On a figure, lasso points to note them. Your agent can leave notes too."
            action={{ href: "/runs/", label: "Open the runs" }}
          />
        ) : (
          <ul className="flex flex-col gap-3">
            {all.map((n) => (
              <li
                key={n.id}
                id={`note-${n.id}`}
                className={cn("rounded-xl border p-4", n.id === id && "ring-foreground/40 ring-2")}
              >
                <NoteCard note={n} links />
              </li>
            ))}
          </ul>
        )
      }
    </QueryState>
  );
}
