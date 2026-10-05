/** Where quotes stand in a text with spaces and line breaks left out, as the server compares a
 * pin's quote with its page: [start, end) in the text as given, in order, overlaps merged. */
export function quoteRanges(text: string, quotes: string[]): [number, number][] {
  const at: number[] = []; // the text's position of each character kept
  let bare = "";
  for (let i = 0; i < text.length; i++)
    if (!/\s/.test(text[i])) {
      at.push(i);
      bare += text[i];
    }
  const found: [number, number][] = [];
  for (const quote of quotes) {
    const want = quote.replace(/\s+/g, "");
    if (!want) continue;
    const i = bare.indexOf(want);
    if (i >= 0) found.push([at[i], at[i + want.length - 1] + 1]);
  }
  found.sort((x, y) => x[0] - y[0]);
  const merged: [number, number][] = [];
  for (const r of found)
    if (merged.length && r[0] <= merged[merged.length - 1][1])
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], r[1]);
    else merged.push([...r]);
  return merged;
}
