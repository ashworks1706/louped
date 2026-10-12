import { expect, test } from "./fixtures";
import { mock } from "./items-run";

// The Hugging Face token on the Hub page: changed or signed out in the app, not in a terminal.
test("the Hugging Face token is changed or removed in the app", async ({ page }) => {
  await mock(page);
  let token = true;
  const asked: string[] = [];
  await page.route("**/api/hub/me", (r) =>
    r.fulfill({
      json: token
        ? { token: true, name: "ash", avatar: null, error: null, env: false }
        : { token: false, name: null, avatar: null, error: null, env: false },
    }),
  );
  await page.route("**/api/hub/added", (r) =>
    r.fulfill({ json: { models: [], embeddings: [], datasets: [] } }),
  );
  await page.route("**/api/hub/token", (r) => {
    asked.push(r.request().method());
    token = r.request().method() === "POST";
    return r.fulfill({
      json: { token, name: token ? "ash" : null, avatar: null, error: null, env: false },
    });
  });
  await page.goto("/hub/");
  await page.getByRole("button", { name: "Change token" }).click();
  await expect(page.getByRole("dialog")).toContainText("replaces the one there");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Connect" })).toBeVisible();
  expect(asked).toEqual(["DELETE"]);
});
