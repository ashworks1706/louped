import type { Page } from "@playwright/test";

// Notes on parts, kept as the server keeps them: a list the page adds to, edits and deletes from.
export type Note = {
  id: string;
  text: string;
  by: "person" | "agent";
  created: string;
  updated: string;
  anchors: {
    part: string;
    url: string;
    run: string | null;
    experiment: string | null;
    shows: string;
    data: unknown;
  }[];
};

/** A note the agent left on item 28 of run m-1. */
export const onRow: Note = {
  id: "n0000001",
  text: "Item 28 flips under **pressure**.",
  by: "agent",
  created: "2026-10-12T08:00:00Z",
  updated: "2026-10-12T08:00:00Z",
  anchors: [
    {
      part: "items/row/28",
      url: "/run/?id=m-1&tab=items",
      run: "m-1",
      experiment: null,
      shows: "28 Water is wet.",
      data: null,
    },
  ],
};

/** Serves /api/notes from a list it changes as the server would; returns the list, newest first,
 * and what each POST asked. */
export async function mockNotes(page: Page, start: Note[] = [onRow]) {
  const notes = [...start];
  const posted: Omit<Note, "id" | "created" | "updated">[] = [];
  await page.route("**/api/notes", (r) => {
    if (r.request().method() !== "POST") return r.fulfill({ json: notes });
    const body = r.request().postDataJSON();
    posted.push(body);
    const now = new Date().toISOString();
    const note = { ...body, id: `n${notes.length + 1000000}`, created: now, updated: now };
    notes.unshift(note);
    return r.fulfill({ json: note });
  });
  await page.route("**/api/notes/*", (r) => {
    const id = decodeURIComponent(new URL(r.request().url()).pathname.split("/").pop()!);
    const at = notes.findIndex((n) => n.id === id);
    if (at < 0) return r.fulfill({ status: 404, json: { detail: `no note ${id}` } });
    if (r.request().method() === "DELETE") {
      notes.splice(at, 1);
      return r.fulfill({ json: null });
    }
    if (r.request().method() === "PUT") {
      const { text } = r.request().postDataJSON();
      notes[at] = { ...notes[at], text, updated: new Date().toISOString() };
    }
    return r.fulfill({ json: notes[at] });
  });
  return { notes, posted };
}
