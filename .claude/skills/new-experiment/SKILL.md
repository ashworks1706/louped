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
4. Write `run.py` using existing tools first (nnsight, Inspect, TRL) and `loupe` where it has the
   piece. Write results under `.loupe/`, with `loupe.core.capture(seed=...).write(...)` next to them.
5. Pin what moves numbers: model revision, seed, greedy decoding unless sampling is the point.
6. If you write something a previous experiment also wrote, stop and move it into `src/loupe`
   instead (with a test), then use it from both.
7. Put the result in **Result** (its first paragraph is what the Experiments page shows: model,
   date, the numbers) and the decision it leads to in **Next**. When a real model's result answers
   the question, set `status: answered`.
