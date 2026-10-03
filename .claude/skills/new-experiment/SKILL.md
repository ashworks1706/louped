---
name: new-experiment
description: Start a research experiment in loupe. Use when the user wants to test an idea, run a study, or reproduce a paper.
---

1. Pick the domain from `DOMAINS` in `src/loupe/stores/experiments.py`: behaviour (mechanisms,
   honesty, conditioning, agents), efficiency (context, inference, specialisation) or checks
   (reproduction). If none fits, propose a new domain rather than forcing one; the steps are under
   "Adding a domain" in `apps/site/content/docs/domains.mdx`.
2. Name the folder for the question, kebab-case: `uv run loupe new <name> --domain <domain>` (New on the Experiments page does the same). It starts
   `active`; set an experiment that the user is not working on now to `parked`.
3. Fill the README before writing code. Each section is one or two sentences:
   - **Question**: comes out yes or no, or as a number.
   - **Observation**: what was seen, separate from what it is thought to mean.
   - **Hypotheses**: including the ones that compete with the user's.
   - **Baseline**: the nearest existing method and the simplest thing that might already work.
   - **Test**: the conditions compared, the metric and seeds. Name correctness and behaviour
     metrics separately; never average them.
   - **Stop if**: the result that would weaken the idea.
4. Fill in the scaffolded `run.py` using existing tools first (nnsight, Inspect, TRL) and `loupe`
   where it has the piece. Its `Args` fields are the Launch form; numbers go to MLflow inside
   `start_run`, figures are views under `views/`, evals are Inspect tasks in `task.py`
   (`apps/site/content/docs/experiments.mdx`). A paper's harness with its own pins runs in its own
   environment, as `rational-updating-baseline/run.py` does.
5. Launch it from the app, or through `loupe mcp` (`launch`, then `job`), so the run shows there.
6. Pin what moves numbers: model revision, seed, greedy decoding unless sampling is the point.
7. If you write something a previous experiment also wrote, stop and move it into `src/loupe`
   instead (with a test), then use it from both.
8. Put the result in **Result** (its first paragraph is what the Experiments page shows: model,
   date, the numbers) and the decision it leads to in **Next**. When a real model's result answers
   the question, set `status: answered`.
