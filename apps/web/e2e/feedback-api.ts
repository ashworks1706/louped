import type { Page } from "@playwright/test";

// Requests for louped itself: the issue forms and one draft an agent wrote.
export const forms = [
  {
    kind: "feature",
    template: "feature.yml",
    fields: [
      { id: "problem", label: "The research task it enables" },
      { id: "prebuilt", label: "Existing tools that already do part of it" },
    ],
  },
  {
    kind: "bug",
    template: "bug.yml",
    fields: [
      { id: "what", label: "What happened, and what you expected" },
      { id: "repro", label: "Steps to reproduce" },
    ],
  },
];

const issue = (title: string) =>
  `https://github.com/ashworks1706/louped/issues/new?template=feature.yml&title=${encodeURIComponent(title)}`;

export const draft = {
  id: "a1b2c3d4",
  kind: "feature",
  title: "Sweep steering layers",
  fields: { problem: "Find the layer where a vector steers best", prebuilt: "nnsight" },
  created: "2026-10-12T00:00:00Z",
  opened: null,
  issue_url: issue("Sweep steering layers"),
};

export async function mockFeedback(page: Page, list: object[] = [draft]) {
  await page.route("**/api/feedback/forms", (r) => r.fulfill({ json: forms }));
  await page.route("**/api/feedback", (r) => r.fulfill({ json: list }));
}

export { issue };
