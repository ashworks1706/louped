import { test as base } from "@playwright/test";

import layout from "./default-layout.json" with { type: "json" };

/** The server's default layout (tests/test_ui.py keeps this file equal to it) and no theme, for
 * pages whose test does not set its own: a test's later page.route wins over these. */
export const DEFAULT_LAYOUT = layout;

export const test = base.extend({
  page: async ({ page }, provide) => {
    await page.route("**/api/ui/layout*", (r) => r.fulfill({ json: layout }));
    await page.route("**/api/ui/theme", (r) =>
      r.fulfill({ json: { light: {}, dark: {}, errors: [] } }),
    );
    await provide(page);
  },
});

export { expect } from "@playwright/test";
