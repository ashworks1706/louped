/** A part's address: its area and kind as written, then its names URL-encoded, so a name with a
 * slash in it (a folder, a file) stays one segment. louped.server.parts lists the kinds. */
export function partId(base: string, ...names: (string | number)[]): string {
  return [base, ...names.map((n) => encodeURIComponent(String(n)))].join("/");
}

/** The props that make an element a part: its address, for Shift+click and the agent's cues. */
export const part = (id: string) => ({ "data-part": id });
