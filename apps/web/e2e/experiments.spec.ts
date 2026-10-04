import { expect, test, type Page } from "@playwright/test";

// A mocked API: one experiment of each status, one with more runs than a card shows, and the
// longest domain title, so grouping, filtering and wrapping are all exercised.
const run = (i: number) => ({
  id: `m-${i}`,
  kind: "eval",
  name: `run ${i}`,
  experiment: "retrieval-injection",
  status: "success",
  created: "2026-09-27T00:00:00Z",
  model: "tiny",
  metrics: { "f1/mean": 0.4 + i / 100 },
  samples: 8,
});

const experiments = [
  {
    name: "refusal-direction",
    axis: "behavior",
    domain: "mechanisms",
    domain_title: "Mechanisms",
    status: "answered",
    question: "Is refusal mediated by a single direction?",
    result: "Ablated at layer 13, harmful refusal goes from 73% to 0%.",
    runs: [],
  },
  {
    name: "sycophancy-pushback",
    axis: "behavior",
    domain: "honesty",
    domain_title: "Sycophancy and honesty",
    status: "parked",
    question: "Does a model cave under pushback?",
    result: null,
    runs: [],
  },
  {
    name: "retrieval-injection",
    axis: "efficiency",
    domain: "context",
    domain_title: "Context and retrieval inside the model",
    status: "active",
    question: "Does injected retrieved state reach the gain of RAG in the prompt?",
    result: "Closed book F1 0.01, RAG 0.46, injected at layer 12 0.00.",
    runs: [1, 2, 3, 4, 5].map(run),
  },
];

async function mockApi(page: Page) {
  await page.route("**/api/experiments", (r) => r.fulfill({ json: experiments }));
  await page.route("**/api/runs", (r) => r.fulfill({ json: [] }));
}

for (const scheme of ["dark", "light"] as const) {
  test(`experiments group by domain and filter by status (${scheme})`, async ({ page }, info) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page);
    await page.goto("/behavior/experiments/");
    await expect(page.getByRole("heading", { level: 2, name: /Mechanisms/ })).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 2, name: /Sycophancy and honesty/ }),
    ).toBeVisible();
    // The efficiency question is on the efficiency page only.
    await expect(page.getByText("retrieval-injection")).toHaveCount(0);
    await page.screenshot({ path: info.outputPath(`experiments-${scheme}.png`), fullPage: true });

    await page.getByRole("button", { name: /parked/i }).click();
    await expect(page).toHaveURL(/status=parked/);
    await expect(page.getByText("sycophancy-pushback")).toBeVisible();
    await expect(page.getByText("refusal-direction")).toHaveCount(0);
    await page.screenshot({ path: info.outputPath(`experiments-parked-${scheme}.png`) });

    await page.goto("/efficiency/experiments/");
    await expect(page.getByText("5 runs")).toBeVisible();
  });
}

test("home shows only the active questions", async ({ page }, info) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 3, name: "retrieval-injection" })).toBeVisible();
  await expect(page.getByText("Context and retrieval inside the model")).toBeVisible();
  await expect(page.getByRole("heading", { name: "refusal-direction" })).toHaveCount(0);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
  await page.screenshot({ path: info.outputPath("home.png"), fullPage: true });
});

test("an experiment page shows its design, result, runs and what launches it", async ({
  page,
}, info) => {
  await mockApi(page);
  const [, , active] = experiments;
  // The page reads its runs from the runs list, as every page does.
  await page.route("**/api/runs", (r) => r.fulfill({ json: active.runs }));
  await page.route("**/api/experiments/retrieval-injection", (r) =>
    r.fulfill({
      json: {
        ...active,
        readme:
          "# retrieval-injection\n\n## Question\n\nDoes it reach the gain?\n\n## Result\n\n| layer | F1 |\n|---|---|\n| 12 | 0.00 |\n",
      },
    }),
  );
  await page.route("**/api/launch", (r) =>
    r.fulfill({
      json: [
        {
          id: "script:retrieval-injection/run.py",
          group: "Experiments",
          title: "retrieval-injection/run.py",
          description: null,
          config: null,
          recipe: null,
        },
      ],
    }),
  );
  await page.goto("/efficiency/experiments/");
  await page
    .getByRole("link", { name: /retrieval-injection/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/efficiency\/experiment\/\?name=retrieval-injection/);
  await expect(page.getByRole("heading", { level: 1, name: "retrieval-injection" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "0.00" })).toBeVisible();
  await expect(page.getByRole("link", { name: "run.py" })).toHaveAttribute(
    "href",
    "/launch/?id=script%3Aretrieval-injection%2Frun.py",
  );
  await page.screenshot({ path: info.outputPath("experiment.png"), fullPage: true });
  await page.getByRole("tab", { name: "Runs (5)" }).click();
  await expect(page.getByText("run 5")).toBeVisible();
});

test("runs filter by kind and status, kept in the URL", async ({ page }) => {
  const runs = [
    { ...experiments[2].runs[0], id: "a", name: "base eval" },
    { ...experiments[2].runs[1], id: "b", name: "sweep", kind: "analysis", status: "finished" },
    { ...experiments[2].runs[2], id: "c", name: "broken", status: "error" },
  ];
  await page.route("**/api/runs", (r) => r.fulfill({ json: runs }));
  await page.goto("/runs/");
  await page.getByLabel("Kind", { exact: true }).selectOption("eval");
  await expect(page).toHaveURL(/kind=eval/);
  await expect(page.getByRole("link", { name: "sweep" })).toHaveCount(0);
  await page.getByLabel("Status").selectOption("failed");
  await expect(page.getByRole("link", { name: "broken" })).toBeVisible();
  await expect(page.getByRole("link", { name: "base eval" })).toHaveCount(0);
  await expect(page).toHaveURL(/state=failed/);
  await page.reload();
  await expect(page.getByLabel("Status")).toHaveValue("failed");
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByRole("link", { name: "sweep" })).toBeVisible();
});

test("compare picks its two runs on the page", async ({ page }) => {
  const runs = [
    { ...experiments[2].runs[0], id: "a", name: "base" },
    { ...experiments[2].runs[1], id: "b", name: "ablated" },
  ];
  await page.route("**/api/runs", (r) => r.fulfill({ json: runs }));
  await page.goto("/compare/");
  await page.getByLabel("Baseline", { exact: true }).selectOption("a");
  await page.getByLabel("Changed", { exact: true }).selectOption("b");
  await expect(page).toHaveURL(/a=a&b=b/);
  await page.getByRole("button", { name: "Swap baseline and changed" }).click();
  await expect(page).toHaveURL(/a=b&b=a/);
});

test("compare queues a judge of the two runs", async ({ page }) => {
  const detail = (id: string) => ({
    ...run(1),
    id,
    name: id,
    params: {},
    tags: {},
    history: {},
    artifacts: [],
    scorers: [],
    error: null,
  });
  await page.route("**/api/runs", (r) => r.fulfill({ json: [run(1), run(2)] }));
  await page.route("**/api/runs/a", (r) => r.fulfill({ json: detail("a") }));
  await page.route("**/api/runs/b", (r) => r.fulfill({ json: detail("b") }));
  await page.route("**/api/runs/*/samples", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/compare?*", (r) =>
    r.fulfill({ json: { a: "a", b: "b", scores: [], only_a: 0, only_b: 0 } }),
  );
  let sent: unknown;
  await page.route("**/api/launch", (r) => {
    sent = r.request().postDataJSON();
    return r.fulfill({ json: { id: "j9", title: "louped judge", status: "queued" } });
  });
  await page.goto("/compare/?a=a&b=b");
  await page.getByRole("button", { name: "Judge", exact: true }).click();
  await expect(page).toHaveURL(/\/launch\/\?id=judge&job=j9/);
  expect(sent).toEqual({ id: "judge", options: { a: "a", b: "b" } });
});

test("a judge run takes your pick and shows the judge's agreement", async ({ page }) => {
  const id = "e-j";
  await page.route("**/api/runs", (r) => r.fulfill({ json: [{ ...run(1), id }] }));
  await page.route(`**/api/runs/${id}`, (r) =>
    r.fulfill({
      json: {
        ...run(1),
        id,
        name: "judge",
        metrics: { "b_wins/mean": 0.5 },
        params: {},
        tags: {},
        history: {},
        artifacts: [],
        scorers: [],
        error: null,
      },
    }),
  );
  await page.route(`**/api/runs/${id}/samples`, (r) =>
    r.fulfill({
      json: [{ id: "1", epoch: 1, input: "q", target: "", scores: { b_wins: 1 }, error: null }],
    }),
  );
  await page.route(`**/api/runs/${id}/samples/1?*`, (r) =>
    r.fulfill({
      json: { id: "1", epoch: 1, target: "", messages: [], scores: [], metadata: {}, error: null },
    }),
  );
  let labels: Record<string, string> = {};
  await page.route(`**/api/runs/${id}/labels`, (r) => r.fulfill({ json: labels }));
  await page.route(`**/api/runs/${id}/labels/1`, (r) => {
    labels = { "1": r.request().postDataJSON().label };
    return r.fulfill({ json: labels });
  });
  await page.route(`**/api/runs/${id}/agreement`, (r) =>
    r.fulfill({
      json: labels["1"]
        ? { labelled: 1, total: 1, agreement: labels["1"] === "b" ? 1 : 0, kappa: null }
        : { labelled: 0, total: 1, agreement: null, kappa: null },
    }),
  );
  await page.goto(`/run/?id=${id}&tab=samples`);
  await expect(page.getByText("Label pairs to check the judge against you.")).toBeVisible();
  await page.getByRole("cell", { name: "q", exact: true }).click();
  const pick = page.getByRole("group", { name: "Your pick" });
  await pick.getByRole("button", { name: "B", exact: true }).click();
  await expect(pick.getByRole("button", { name: "B", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.keyboard.press("Escape");
  await expect(page.getByText(/Agrees with you on/)).toContainText("100.0%");
});

test("the command menu jumps to an experiment", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcut");
  await mockApi(page);
  await page.goto("/");
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("sycophancy");
  await expect(page.getByRole("option", { name: /sycophancy-pushback/ })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/experiment\/\?name=sycophancy-pushback/);
});
