import type { Page } from "@playwright/test";

import { pdf } from "./sources-api";

// reports/ over a mocked API: a Markdown write-up that cites a source and shows a live number,
// a deck on experiment hello, a PDF, and an exported figure filed by its folder.
const at = "2026-10-05T12:00:00Z";
const on = { experiment: "hello", runs: ["m-1"] };
export const reports = [
  { path: "1b.md", kind: "md", size: 120, modified: at, ref: null, ...on },
  { path: "lab.pptx", kind: "pptx", size: 30000, modified: at, ref: null, ...on },
  {
    path: "paper.pdf",
    kind: "pdf",
    size: 900,
    modified: at,
    ref: null,
    experiment: null,
    runs: [],
  },
  {
    path: "figures/bars.svg",
    kind: "svg",
    size: 2048,
    modified: at,
    ref: "run:m-1/views/bars.json",
    experiment: null,
    runs: ["m-1", "m-2", "m-3"],
  },
];
const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><rect width="60" height="40"/></svg>';

/** Mocks reports/; `preview` says whether LibreOffice draws the deck. */
export async function mockReports(page: Page, preview = false) {
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/reports", reports);
  await page.route("**/api/reports/outline?*", (r) => {
    const path = new URL(r.request().url()).searchParams.get("path");
    return r.fulfill({
      json:
        path === "1b.md"
          ? [
              "# 1B\n\nModels cave [@pushback p1], 0.92 in `run:m-1`.\n\n" +
                "Accuracy {{run:m-1 accuracy :.0%}}, then {{run:m-1 gone}}.\n\n" +
                "{{run:m-1/views/bars.json}}\n",
            ]
          : ["Caving rate 0.92\nSource: run:m-1", "", "Evidence helps"],
    });
  });
  await page.route("**/api/live?*", (r) =>
    r.fulfill({
      json: [
        { text: "run:m-1 accuracy :.0%", ref: "run:m-1", metric: "accuracy", value: "92%" },
        {
          text: "run:m-1 gone",
          ref: "run:m-1",
          metric: "gone",
          error: "run m-1 has no metric gone",
        },
        {
          text: "run:m-1/views/bars.json",
          ref: "run:m-1/views/bars.json",
          view: {
            kind: "table",
            title: "Caving by condition",
            columns: ["condition", "caved"],
            rows: [["pressure", 0.92]],
          },
        },
      ],
    }),
  );
  await page.route("**/api/reports/preview?*", (r) =>
    preview
      ? r.fulfill({ body: pdf("Caving rate", "Evidence helps"), contentType: "application/pdf" })
      : r.fulfill({
          status: 501,
          json: { detail: "LibreOffice is not installed, so louped cannot draw this file." },
        }),
  );
  await page.route("**/api/reports/file?*", (r) => {
    const path = new URL(r.request().url()).searchParams.get("path");
    return path === "paper.pdf"
      ? r.fulfill({
          body: pdf("Page one", "Page two", "Page three"),
          contentType: "application/pdf",
        })
      : r.fulfill({ body: svg, contentType: "image/svg+xml" });
  });
}
