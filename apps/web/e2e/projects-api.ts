import type { Page } from "@playwright/test";

import { experiment, summary } from "./items-run";

// The project's projects over a mocked API: pushback holds experiment hello (with its run m-1),
// and gone is a name an experiment gives with no README.
const hello = { ...experiment, project: "pushback", readme: undefined };
export const orphan = {
  ...hello,
  name: "second-turn",
  status: "parked",
  question: "Does a second turn undo it?",
  project: "gone",
  runs: [],
};
export const pushback = {
  name: "pushback",
  title: "Sycophancy under pushback",
  status: "active",
  summary: "When and why models cave when a user pushes back.",
  tags: ["honesty", "multi-turn"],
  links: {
    repo: "https://github.com/me/pushback",
    paper: "https://arxiv.org/abs/2310.13548",
  },
  models: ["Qwen/Qwen2.5-0.5B-Instruct"],
  datasets: [],
  benchmarks: ["inspect_evals/truthfulqa"],
  missing: false,
};
export const projects = [
  {
    ...pushback,
    experiments: ["hello"],
    runs: 1,
    last_run: summary.created,
  },
  {
    ...pushback,
    name: "gone",
    title: "gone",
    summary: "",
    tags: [],
    links: {},
    models: [],
    benchmarks: [],
    experiments: ["second-turn"],
    runs: 0,
    last_run: null,
    missing: true,
  },
];
export const readme = "# Sycophancy under pushback\n\n## Goal\n\nFind when a model caves.\n";
export const detail = {
  ...pushback,
  readme,
  experiments: [hello],
  runs: [summary],
};
const goneDetail = {
  ...projects[1],
  readme: "",
  experiments: [orphan],
  runs: [],
};
export const domains = [
  { key: "honesty", axis: "behavior", title: "Sycophancy and honesty" },
  { key: "inference", axis: "efficiency", title: "Inference cost and kernels" },
];

/** The projects, one project, the domains, and the experiments naming them. */
export async function mockProjects(page: Page) {
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/projects", projects);
  await json("**/api/projects/pushback", detail);
  await json("**/api/projects/gone", goneDetail);
  await json("**/api/domains", domains);
  await json("**/api/experiments", [hello]);
  await json("**/api/experiments/hello", { ...experiment, project: "pushback" });
}
