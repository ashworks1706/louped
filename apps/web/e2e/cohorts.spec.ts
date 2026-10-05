import { expect, test } from "./fixtures";
import { mock, stats } from "./items-run";

// Items picked on a run's Items tab become a cohort: every condition read on just them, with its
// paired interval, saved in the experiment and run again on just them.
const saved = {
  name: "flipped",
  ids: ["28"],
  run: "m-1",
  folder: "raw",
  key: "qid",
  note: "Pushback flipped these.",
  created: "2026-10-05T00:00:00Z",
};

test("a saved cohort reads every condition on its items, with the paired interval", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/experiments/hello/cohorts", (r) => r.fulfill({ json: [saved] }));
  const asked: unknown[] = [];
  await page.route("**/api/runs/m-1/cohort", (r) => {
    const body = r.request().postDataJSON();
    asked.push(body);
    return r.fulfill({ json: stats(body.ids) });
  });
  await page.goto("/run/?id=m-1&tab=items");
  const pressure = page.locator('[data-part="items/stat/pressure"]');
  await expect(pressure).toContainText("Δ -50.0 pts · -100.0 to 0.0");
  await page.locator('[data-part="items/cohort"] select').selectOption("flipped");
  await expect(page).toHaveURL(/cohort=flipped/);
  await expect(page.locator('[data-part="items/count"]')).toHaveText("1 of 1 items");
  await expect(page.locator('[data-part="items/cohort/note"]')).toHaveText(
    "Pushback flipped these.",
  );
  await expect(pressure).toContainText("0/1"); // the rate on the cohort's one item
  await expect
    .poll(() => asked.at(-1))
    .toMatchObject({ ids: ["28"], folder: "raw", field: "correct", reference: "baseline" });

  await page.goto("/run/?id=m-1&tab=items&cohort=gone");
  await expect(page.getByText("This experiment has no cohort gone.")).toBeVisible();
});

test("picked rows are read alone, saved as a cohort and run again", async ({ page }, info) => {
  test.skip(info.project.name === "mobile", "Shift is a keyboard's");
  await mock(page);
  let body: unknown;
  await page.route("**/api/experiments/hello/cohorts/*", (r) => {
    body = r.request().postDataJSON();
    return r.fulfill({ json: { ...saved, name: "two", ids: ["28", "29"] } });
  });
  await page.route("**/api/launch", (r) =>
    r.fulfill({
      json: [
        {
          id: "script:hello/run.py",
          group: "Experiments",
          title: "hello/run.py",
          description: "",
          config: null,
          recipe: null,
        },
      ],
    }),
  );
  await page.route("**/api/launch/options*", (r) =>
    r.fulfill({
      json: [
        { flag: "--seed", kind: "text", default: "0", help: "", choices: [], required: false },
        { flag: "--cohort", kind: "text", default: "None", help: "", choices: [], required: false },
      ],
    }),
  );
  await page.goto("/run/?id=m-1&tab=items");
  for (const id of ["28", "29"])
    await page
      .locator(`[data-part="items/row/${id}"] td`)
      .first()
      .click({ modifiers: ["Shift"] });
  const tray = page.getByRole("region", { name: "Picked parts" });
  await tray.getByRole("button", { name: "Only these" }).click();
  await expect(page).toHaveURL(/ids=28%2C29|ids=28,29/);
  await expect(page.locator('[data-part="items/cohort"] select')).toHaveValue("*picked");

  await tray.getByRole("button", { name: "Save cohort" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("two");
  await dialog.getByLabel("What they have in common").fill("Both answered.");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect
    .poll(() => body)
    .toEqual({ ids: ["28", "29"], note: "Both answered.", run: "m-1", folder: "raw", key: "qid" });
  await page.getByRole("button", { name: "Run on it" }).click();
  await expect(page).toHaveURL(/\/launch\/\?id=script%3Ahello%2Frun\.py&cohort=two/);
  await expect(page.getByText("--cohort two")).toBeVisible();
});

test("records that don't say what the item is say so, and no reply stands in for it", async ({
  page,
}) => {
  await mock(page);
  const reply = (condition: string, pred: string) => ({
    qid: 28,
    gold: "True",
    pred,
    correct: pred === "True" ? 1 : 0,
    response: `A long reply from ${condition}, which is not the item itself at all.`,
  });
  for (const [name, pred] of [
    ["baseline", "True"],
    ["pressure", "False"],
  ])
    await page.route(`**/api/runs/m-1/artifacts/raw/${name}.jsonl`, (r) =>
      r.fulfill({ body: JSON.stringify(reply(name, pred)) + "\n" }),
    );
  await page.goto("/run/?id=m-1&tab=items");
  await expect(page.locator('[data-part="items/column/response"]')).toHaveCount(0);
  await page.locator('[data-part="items/row/28"]').click();
  await expect(page.locator('[data-part="item/title"]')).toContainText(
    "These records don't say what the item is",
  );
});
