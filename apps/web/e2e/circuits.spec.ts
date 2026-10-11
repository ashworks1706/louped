import { expect, test } from "./fixtures";
import { mockPages } from "./pages-api";

// An attribution graph drawn by louped: prune it, walk it, pin nodes, save the pins.
test("a circuit is pruned, walked and pinned", async ({ page }, info) => {
  await mockPages(page);
  await page.route("**/api/graphs", (r) =>
    r.fulfill({
      json: [
        { slug: "a", prompt: "first", scan: null },
        { slug: "capital", prompt: "The capital of France is", scan: null },
      ],
    }),
  );
  await page.goto("/behavior/circuits/?keep=0.99&edges=1");
  await expect(page.locator('[data-part="circuits/stat/output"]')).toContainText("Paris");
  await expect(page.getByRole("link", { name: "circuit-tracer viewer" })).toHaveAttribute(
    "href",
    /\/circuit\/\?slug=capital$/,
  );
  const nodes = page.locator('[data-part^="circuits/node/"]');
  await expect(nodes).toHaveCount(12);
  await page.screenshot({ path: info.outputPath("circuits.png"), fullPage: true });

  // a node shows what it reads from and writes to
  await page.getByRole("button", { name: "say Paris, feature, layer 2" }).click();
  await expect(page).toHaveURL(/node=2_7_4/);
  const detail = page.locator('[data-part="circuits/node-detail/2_7_4"]');
  await expect(detail.getByRole("heading", { name: "say Paris" })).toBeVisible();
  await expect(detail).toContainText("55.0%");
  await detail.getByRole("button", { name: /^France/ }).click();
  await expect(page).toHaveURL(/node=0_11_3/);

  // arrow keys walk to the strongest output; P pins
  await page.getByRole("button", { name: "France, feature, layer 0" }).focus();
  await page.keyboard.press("ArrowUp");
  await expect(page).toHaveURL(/node=2_7_4/);
  await page.keyboard.press("p");
  await page.getByRole("button", { name: "France, feature, layer 0" }).click();
  await page.locator('[data-part="circuits/pin"]').click();
  const pinned = page.locator('[data-part="circuits/pinned"]');
  await expect(pinned).toContainText("say Paris");
  await expect(pinned).toContainText("France");

  // pinned only, then grouped into one node
  await page.getByRole("button", { name: "Pinned (2)" }).click();
  await expect(nodes).toHaveCount(2);
  await page.getByLabel("Group name").fill("france route");
  await page.getByRole("button", { name: "Group", exact: true }).click();
  await expect(nodes).toHaveCount(1);
  await expect(page.locator('[data-part="circuits/node/group%3Afrance%20route"]')).toBeVisible();

  const saved = page.waitForRequest(
    (r) => r.url().endsWith("/api/graphs/capital/pins") && r.method() === "PUT",
  );
  await page.locator('[data-part="circuits/save"]').click();
  expect((await saved).postDataJSON()).toEqual({
    pinned: ["2_7_4", "0_11_3"],
    groups: [{ name: "france route", nodes: ["2_7_4", "0_11_3"] }],
  });

  // a lower share keeps fewer nodes
  await page.getByRole("button", { name: "Pruned graph" }).click();
  await page.locator("#circuit-keep").fill("0.3");
  await expect(page).toHaveURL(/keep=0.3/);
  expect(await nodes.count()).toBeLessThan(12);
  await page.screenshot({ path: info.outputPath("circuits-pruned.png"), fullPage: true });
});
