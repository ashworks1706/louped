import { expect, test } from "@playwright/test";

const run = {
  id: "m-1",
  kind: "analysis",
  name: "custom chart",
  experiment: "hello",
  status: "finished",
  created: null,
  model: null,
  metrics: {},
  samples: null,
  params: {},
  tags: {},
  history: {},
  artifacts: [{ path: "views/00-v.json", size: 1 }],
  scorers: [],
  error: null,
  log: null,
};
const vega = {
  kind: "vega",
  title: "flip rate by turn",
  spec: {
    mark: "bar",
    data: {
      values: [
        { turn: "first", rate: 0.2 },
        { turn: "second", rate: 0.5 },
      ],
    },
    encoding: {
      x: { field: "turn", type: "nominal" },
      y: { field: "rate", type: "quantitative" },
    },
  },
  note: null,
  about: null,
};

for (const scheme of ["dark", "light"] as const) {
  test(`a vega view draws the chart its spec describes in ${scheme}`, async ({ page }, info) => {
    await page.addInitScript((t) => localStorage.setItem("theme", t), scheme);
    await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: run }));
    await page.route("**/api/runs/m-1/views", (r) =>
      r.fulfill({ json: [{ path: "views/00-v.json", view: vega }] }),
    );
    await page.goto("/run/?id=m-1&tab=figures");
    const figure = page.locator("figure").filter({ hasText: vega.title });
    await expect(figure.locator("svg .mark-rect path")).toHaveCount(2);
    await expect(figure.getByText("second")).toBeVisible();
    await figure.locator("svg .mark-rect path").last().hover();
    await expect(page.locator("#vg-tooltip-element")).toContainText("0.5");
    await page.screenshot({ path: info.outputPath(`vega-${scheme}.png`), fullPage: true });
  });
}

test("Runs offers Push and Pull when the project has a remote", async ({ page }, info) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({
      json: { status: "ok", version: "0", home: "/x", launching: true, remote: "hf://buckets/a/b" },
    }),
  );
  await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/runs", (r) => r.fulfill({ json: [] }));
  let pushed = false;
  await page.route("**/api/launch/push", (r) => {
    pushed = true;
    return r.fulfill({ json: { remote: "hf://buckets/a/b", bundle: "x", runs: ["m-1"] } });
  });
  await page.goto("/runs/");
  await expect(page.getByRole("button", { name: "Pull" })).toBeVisible();
  await page.getByRole("button", { name: "Push" }).click();
  await expect(page.getByText("1 runs pushed")).toBeVisible();
  expect(pushed).toBe(true);
  await page.screenshot({ path: info.outputPath("runs-remote.png"), fullPage: true });
});

test("a missing token opens Connect, which sets the remote", async ({ page }, info) => {
  let remote: string | null = null;
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", version: "0", home: "/x", launching: true, remote } }),
  );
  await page.route("**/api/launch/jobs", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/runs", (r) => r.fulfill({ json: [] }));
  const sent: unknown[] = [];
  await page.route("**/api/launch/remote", (r) => {
    sent.push(r.request().postDataJSON());
    remote = "hf://buckets/ash/proj";
    return r.fulfill({ json: { remote, token: true } });
  });
  await page.route("**/api/launch/pull", (r) =>
    r.fulfill({ status: 401, json: { detail: "needs a Hugging Face token" } }),
  );
  await page.goto("/runs/");
  await page.getByRole("button", { name: "Connect" }).click();
  const dialog = page.getByRole("dialog", { name: "Connect a remote" });
  await dialog.getByLabel("Hugging Face token").fill("hf_x");
  await page.screenshot({ path: info.outputPath("connect.png") });
  await dialog.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByText("Remote set")).toBeVisible();
  expect(sent).toEqual([{ remote: "", token: "hf_x" }]);
  await page.getByRole("button", { name: "Pull" }).click(); // the token is gone again: asked, not failed
  await expect(page.getByRole("dialog", { name: "Connect a remote" })).toBeVisible();
  await expect(page.getByText("Pull failed")).toHaveCount(0);
  await expect(dialog.getByLabel("Remote")).toHaveValue("hf://buckets/ash/proj");
});

test("a vega spec that loads data from a url is refused", async ({ page }) => {
  const remote = { ...vega, spec: { ...vega.spec, data: { url: "https://example.com/x.csv" } } };
  let asked = false;
  await page.route("https://example.com/**", (r) => {
    asked = true;
    return r.fulfill({ body: "turn,rate\n" });
  });
  await page.route("**/api/runs/m-1", (r) => r.fulfill({ json: run }));
  await page.route("**/api/runs/m-1/views", (r) =>
    r.fulfill({ json: [{ path: "views/00-v.json", view: remote }] }),
  );
  await page.goto("/run/?id=m-1&tab=figures");
  await expect(page.getByText(/data must be inline/)).toBeVisible();
  expect(asked).toBe(false);
});

test("a published page reads its answers from files", async ({ page }) => {
  // what `louped publish` writes: each answer at api/<encodeURIComponent(path), % as ,>.json
  const file = (path: string) => `**/api/${encodeURIComponent(path).replaceAll("%", ",")}.json`;
  await page.route("**/run/**", async (r) => {
    const res = await r.fetch();
    const html = (await res.text()).replace(
      "<head>",
      '<head><meta name="louped-snapshot" content="1">',
    );
    return r.fulfill({ response: res, body: html });
  });
  await page.route(file("/health"), (r) =>
    r.fulfill({
      json: { status: "ok", version: "0", home: "/x", launching: false, remote: null },
    }),
  );
  await page.route(file("/runs/m-1"), (r) => r.fulfill({ json: run }));
  await page.route(file("/runs/m-1/views"), (r) =>
    r.fulfill({ json: [{ path: "views/00-v.json", view: vega }] }),
  );
  await page.goto("/run/?id=m-1&tab=figures");
  await expect(page.locator("figure").filter({ hasText: vega.title })).toBeVisible();
});
