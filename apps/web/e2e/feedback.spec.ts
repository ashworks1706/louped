import { draft, issue, mockFeedback } from "./feedback-api";
import { expect, test } from "./fixtures";
import { mock } from "./items-run";

// The Feedback page: a request an agent drafted is read, edited, saved and filed on GitHub
// through its prefilled new-issue page; louped itself sends nothing.
test("a drafted request is edited, saved, then opened on GitHub", async ({ page }, info) => {
  await mock(page);
  await mockFeedback(page);
  const sent: { method: string; url: string; body: unknown }[] = [];
  await page.route("**/api/feedback/a1b2c3d4**", (r) => {
    const req = r.request();
    sent.push({ method: req.method(), url: req.url(), body: req.postDataJSON() });
    const title = (req.postDataJSON() as { title?: string } | null)?.title ?? draft.title;
    saved = { ...draft, title, issue_url: issue(title) };
    return r.fulfill({ json: saved });
  });
  let saved = draft;
  await page.route("**/api/feedback", (r) => r.fulfill({ json: [saved] }));
  await page.goto("/feedback/");
  await expect(page.getByRole("heading", { level: 1, name: "Feedback" })).toBeVisible();
  await expect(page.locator('[data-part="feedback/item/a1b2c3d4"]')).toContainText("draft");
  await expect(page.getByLabel("The research task it enables")).toHaveValue(
    "Find the layer where a vector steers best",
  );
  const open = page.locator('[data-part="feedback/open"]');
  await expect(open).toHaveAttribute("href", draft.issue_url);
  await expect(open).toHaveAttribute("target", "_blank");
  await page.screenshot({ path: info.outputPath("feedback.png"), fullPage: true });

  // an edit must be saved before it can be filed: GitHub gets what is saved
  await page.getByLabel("Title").fill("Sweep every steering layer");
  await expect(open).toBeDisabled();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect
    .poll(() => sent.find((s) => s.method === "PUT")?.body)
    .toEqual({
      kind: "feature",
      title: "Sweep every steering layer",
      fields: draft.fields,
    });
  await expect(open).toHaveAttribute("href", issue("Sweep every steering layer"));

  const popup = page.waitForEvent("popup");
  await page.route("https://github.com/**", (r) => r.fulfill({ body: "github" }));
  await open.click();
  await (await popup).close();
  await expect.poll(() => sent.some((s) => s.url.endsWith("/opened"))).toBe(true);
});

test("with no requests, a person writes one", async ({ page }) => {
  await mock(page);
  await mockFeedback(page, []);
  const posted: unknown[] = [];
  await page.route("**/api/feedback", (r) => {
    if (r.request().method() !== "POST") return r.fulfill({ json: posted.length ? [draft] : [] });
    posted.push(r.request().postDataJSON());
    return r.fulfill({ json: { ...draft, kind: "bug", title: "Crash", fields: {} } });
  });
  await page.goto("/feedback/");
  await expect(page.getByText("No requests yet")).toBeVisible();
  await page.getByRole("button", { name: "New request" }).click();
  await expect(page).toHaveURL(/id=new/);
  await page.getByRole("button", { name: "Bug" }).click();
  await page.getByLabel("Title").fill("Crash");
  await page.getByLabel("What happened, and what you expected").fill("It crashed");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect
    .poll(() => posted[0])
    .toEqual({ kind: "bug", title: "Crash", fields: { what: "It crashed" } });
  await expect(page).toHaveURL(/id=a1b2c3d4/);
});

test("a shared server keeps no requests, and the sidebar hides Feedback", async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching: false, remote: null } }),
  );
  await page.goto("/feedback/");
  await expect(page.getByText("Feedback is off here")).toBeVisible();
  await expect(page.locator('[data-part="shell/nav/%2Ffeedback%2F"]')).toHaveCount(0);
});
