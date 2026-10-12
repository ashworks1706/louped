import { expect, test } from "./fixtures";
import { mock, run } from "./items-run";
import { mockNotes, onRow } from "./notes-api";

// Notes on any part: Shift+click parts, Note in the tray, and the note shows as a mark on them;
// the Notes page lists every note and opens each one's page; a lasso on a figure notes its points.

test("a note written on picked parts shows as a mark on them, edited and deleted", async ({
  page,
}, info) => {
  test.skip(info.project.name === "mobile", "Shift is a keyboard's");
  await mock(page);
  const { posted } = await mockNotes(page, []);
  await page.route("**/api/ui/selection", (r) =>
    r.fulfill({ json: { parts: [], version: 1, read: 0 } }),
  );
  await page.goto("/run/?id=m-1&tab=items");
  const row = page.locator('[data-part="items/row/29"]');
  await row
    .locator("td")
    .first()
    .click({ modifiers: ["Shift"] });
  const tray = page.getByRole("region", { name: "Picked parts" });
  await tray.getByRole("button", { name: "Note" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Note on row / 29");
  await dialog.getByRole("textbox", { name: "Note" }).fill("Abstains under pressure");
  await dialog.getByRole("button", { name: "Keep note" }).click();
  await expect(tray).toBeHidden(); // the picks are noted, so the tray clears
  expect(posted).toHaveLength(1);
  expect(posted[0]).toMatchObject({
    text: "Abstains under pressure",
    by: "person",
    anchors: [{ part: "items/row/29", url: "/run/?id=m-1&tab=items", run: "m-1" }],
  });
  expect(posted[0].anchors[0].shows).toContain("Fire is cold.");

  const mark = page.getByRole("button", { name: "1 note on row / 29" });
  await expect(mark).toBeVisible();
  await mark.click();
  const notes = page.getByRole("dialog", { name: "Notes on row / 29" });
  await expect(notes).toContainText("Abstains under pressure");
  await expect(notes).toContainText("You");
  await page.screenshot({ path: info.outputPath("note-mark.png") });

  await notes.getByRole("button", { name: "Edit note" }).click();
  await notes.getByRole("textbox", { name: "Note" }).fill("Abstains, then holds");
  await notes.getByRole("button", { name: "Save" }).click();
  await expect(notes).toContainText("Abstains, then holds");

  await notes.getByRole("button", { name: "Delete note" }).click();
  await notes.getByRole("button", { name: "Delete" }).click(); // the one confirm
  await expect(mark).toBeHidden();
});

test("the Notes page lists every note and opens one on its part", async ({ page }, info) => {
  await mock(page);
  await mockNotes(page);
  await page.goto("/notes/");
  const card = page.locator(`[data-part="notes/note/${onRow.id}"]`);
  await expect(card).toContainText("Item 28 flips under pressure.");
  await expect(card).toContainText("Your agent");
  await page.screenshot({ path: info.outputPath("notes-page.png"), fullPage: true });
  await card.getByRole("link", { name: "row / 28 · m-1" }).click();
  await expect(page).toHaveURL(/\/run\/\?id=m-1&tab=items&note=n0000001/);
  // the link opens the note beside its part
  await expect(page.getByRole("dialog", { name: "Notes on row / 28" })).toContainText(
    "Item 28 flips under pressure.",
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Notes on row / 28" })).toBeHidden();
});

test("a note on another run's part does not show here", async ({ page }) => {
  await mock(page);
  await mockNotes(page, [{ ...onRow, anchors: [{ ...onRow.anchors[0], run: "m-9" }] }]);
  await page.goto("/run/?id=m-1&tab=items");
  await expect(page.locator('[data-part="items/row/28"]')).toBeVisible();
  await expect(page.getByRole("button", { name: /note on row/ })).toHaveCount(0);
});

test("no notes yet says how to write one", async ({ page }) => {
  await mock(page);
  await page.goto("/notes/");
  await expect(page.getByText("No notes yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the runs" })).toBeVisible();
});

const scatter = {
  kind: "plotly",
  title: "Claims",
  items: true,
  data: [{ type: "scatter", mode: "markers", name: "claims", x: [0, 1, 2], y: [2, 1, 0],
           ids: ["28", "29", "30"] }], // prettier-ignore
};

test("a lasso on a figure keeps a note on the points it holds", async ({ page }, info) => {
  await mock(page);
  const { posted } = await mockNotes(page, []);
  const withViews = {
    ...run,
    artifacts: [...run.artifacts, { path: "views/claims.json", size: 1 }],
  };
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: withViews }));
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/claims.json", view: scatter }] }),
  );
  await page.goto("/run/?id=m-1&tab=figures");
  const plot = page.getByTestId("plotly");
  await expect(plot.locator(".main-svg").first()).toBeVisible({ timeout: 15_000 });
  // what Plotly's Lasso Select reports for a lasso around the first two points
  await plot.evaluate((el) => {
    const gd = el as unknown as {
      data: object[];
      emit: (event: string, e: object) => void;
    };
    const data = gd.data[0];
    gd.emit("plotly_selected", {
      points: [0, 1].map((i) => ({ curveNumber: 0, pointNumber: i, x: i, y: 2 - i, data })),
      lassoPoints: { x: [-0.5, 1.5, 1.5], y: [2.5, 2.5, 0.5] },
    });
  });
  const held = page.locator('[data-part="figures/lasso/views%2Fclaims.json"]');
  await expect(held).toContainText("2 points drawn around · 2 items");
  await held.getByRole("button", { name: "Note" }).click();
  await page.getByRole("textbox", { name: "Note" }).fill("These two cave together");
  await page.getByRole("button", { name: "Keep note" }).click();
  await expect(held).toBeHidden();
  expect(posted[0].anchors[0]).toMatchObject({
    part: "figures/figure/views%2Fclaims.json",
    run: "m-1",
    shows: "2 points of Claims",
    data: {
      count: 2,
      items: ["28", "29"],
      points: [
        { trace: "claims", x: 0, y: 2, id: "28" },
        { trace: "claims", x: 1, y: 1, id: "29" },
      ],
      region: { lasso: { x: [-0.5, 1.5, 1.5], y: [2.5, 2.5, 0.5] } },
    },
  });
  await expect(
    page.getByRole("button", { name: "1 note on figure / views/claims.json" }),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("lasso-note.png"), fullPage: true });
});
