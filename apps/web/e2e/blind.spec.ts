import { expect, test } from "./fixtures";

// Blind A/B on Compare: pairs with hidden sides, picked by key, and the result once revealed.
const detail = (id: string) => ({
  id,
  kind: "eval",
  name: id,
  experiment: "hello",
  status: "success",
  created: "2026-10-01T00:00:00Z",
  model: "tiny",
  metrics: {},
  samples: 2,
  params: {},
  tags: {},
  history: {},
  artifacts: [],
  scorers: [],
  error: null,
});

test("blind A/B picks by key without saying which run is which", async ({ page }, info) => {
  const pairs = [
    { sample: "1", request: "Is water wet?", left: "Yes, it is.", right: "No.", pick: null },
    { sample: "2", request: "Is fire cold?", left: "Yes.", right: "No, it is hot.", pick: null },
  ];
  const sent: object[] = [];
  await page.route("**/api/runs", (r) => r.fulfill({ json: [detail("e-a"), detail("e-b")] }));
  await page.route("**/api/runs/e-a", (r) => r.fulfill({ json: detail("e-a") }));
  await page.route("**/api/runs/e-b", (r) => r.fulfill({ json: detail("e-b") }));
  await page.route("**/api/runs/*/samples", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/compare?*", (r) =>
    r.fulfill({ json: { a: "e-a", b: "e-b", scores: [], only_a: 0, only_b: 0 } }),
  );
  const session = () => ({
    a: "e-a",
    b: "e-b",
    pairs,
    labelled: pairs.filter((p) => p.pick).length,
  });
  await page.route("**/api/ab?*", (r) => r.fulfill({ json: session() }));
  await page.route("**/api/ab/pick", (r) => {
    const body = r.request().postDataJSON();
    sent.push(body);
    pairs.find((p) => p.sample === body.sample)!.pick = body.side;
    return r.fulfill({ json: session() });
  });
  await page.route("**/api/ab/result?*", (r) =>
    r.fulfill({
      json: {
        a: "e-a",
        b: "e-b",
        labelled: 2,
        total: 2,
        a_wins: 1,
        b_wins: 0,
        ties: 1,
        b_rate: 0.25,
        low: 0,
        high: 0.5,
        judges: [{ run: "e-j", labelled: 2, agreement: 0.5, kappa: 0 }],
      },
    }),
  );
  await page.goto("/compare/?a=e-a&b=e-b");
  await page.locator('[data-part="compare/blind/open"]').click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText("Is water wet?")).toBeVisible();
  await expect(sheet.locator('[data-part="compare/blind/reveal"]')).toBeDisabled();
  await expect(sheet).not.toContainText("e-a");
  await page.keyboard.press("1");
  await expect(sheet.getByText("Is fire cold?")).toBeVisible();
  await page.keyboard.press("0");
  await expect
    .poll(() => sent)
    .toEqual([
      { a: "e-a", b: "e-b", sample: "1", side: "left" },
      { a: "e-a", b: "e-b", sample: "2", side: "tie" },
    ]);
  await expect(sheet.locator('[data-part="compare/blind/result"]')).toHaveCount(0);
  await sheet.locator('[data-part="compare/blind/reveal"]').click();
  const result = sheet.locator('[data-part="compare/blind/result"]');
  await expect(result).toContainText("25.0%");
  await expect(result.locator('[data-part="compare/blind/judge/e-j"]')).toContainText("50.0%");
  await expect(sheet.locator('[data-part="compare/blind/tie"]')).toBeDisabled();
  await page.keyboard.press("2");
  expect(sent).toHaveLength(2); // revealed, the picks are locked
  await page.screenshot({ path: info.outputPath("blind.png") });
});
