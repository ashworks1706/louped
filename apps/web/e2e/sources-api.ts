import type { Page } from "@playwright/test";

// The project's sources over a mocked API: a two-page PDF fetched from arXiv and a slide deck,
// with one passage of the PDF pinned.

/** A small PDF with one line of text on each page, as tests/test_sources.py makes one. */
export function pdf(...pages: string[]): Buffer {
  const objs = ["<< /Type /Catalog /Pages 2 0 R >>", ""];
  const kids: string[] = [];
  const font = 3 + 2 * pages.length;
  pages.forEach((text, i) => {
    const [page, content] = [3 + 2 * i, 4 + 2 * i];
    kids.push(`${page} 0 R`);
    const stream = `BT /F1 24 Tf 72 720 Td (${text}) Tj ET`;
    objs.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${content} 0 R` +
        ` /Resources << /Font << /F1 ${font} 0 R >> >> >>`,
    );
    objs.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  });
  objs[1] = `<< /Type /Pages /Kids [${kids.join(" ")}] /Count ${pages.length} >>`;
  objs.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((body, n) => {
    offsets.push(out.length);
    out += `${n + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

export const paper = {
  key: "pushback",
  title: "Towards Understanding Sycophancy in Language Models",
  kind: "pdf",
  file: "pushback.pdf",
  origin: "https://arxiv.org/abs/2310.13548",
  sha256: "a".repeat(64),
  added: "2026-10-05T00:00:00Z",
  pages: 2,
};
export const deck = {
  ...paper,
  key: "deck",
  title: "Lab meeting",
  kind: "pptx",
  file: "deck.pptx",
  origin: null,
  sha256: "b".repeat(64),
};
export const notebook = {
  ...paper,
  key: "explore",
  title: "Explore",
  kind: "ipynb",
  file: "explore.ipynb",
  origin: null,
  sha256: "c".repeat(64),
};
export const pinned = {
  id: "5b55feb4d5",
  key: "pushback",
  page: 1,
  exact: "cave to pushback",
  start: 7,
  note: "the caving claim",
  links: ["experiment:hello"],
  created: "2026-10-05T00:00:00Z",
};

export async function mockSources(page: Page) {
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/sources", [deck, notebook, paper]);
  await json("**/api/sources/search?*", [
    { key: "pushback", title: paper.title, page: 1, snippet: "Models cave to [pushback]" },
  ]);
  await page.route("**/api/sources/pushback/file?*", (r) =>
    r.fulfill({
      body: pdf("Models cave to pushback", "Evidence helps them"),
      contentType: "application/pdf",
    }),
  );
  await json("**/api/sources/deck/pages/*", {
    key: "deck",
    page: 1,
    text: "Caving rate by condition",
  });
  await json("**/api/sources/explore/pages/*", { key: "explore", page: 1, text: "n = 2" });
  await page.route("**/api/sources/explore/notebook?*", (r) =>
    r.fulfill({
      body: '<html><body><main class="jp-Notebook"><p>printed 4</p></main></body></html>',
      contentType: "text/html",
    }),
  );
  await page.route("**/api/pins?*", (r) => {
    const key = new URL(r.request().url()).searchParams.get("key");
    return r.fulfill({ json: key === "pushback" ? [pinned] : [] });
  });
}
