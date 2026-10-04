---
name: new-experiment
description: Start a research experiment in a loupe project. Use when the user wants to test an idea, run a study, or reproduce a paper.
---

1. Read what exists first: the `experiments` MCP tool, or `experiments/`. Extend an experiment
   that already asks the question instead of starting another.
2. Pick the domain: one the project's `loupe.toml` lists, else loupe's own (mechanisms, honesty,
   conditioning, agents; context, inference, specialisation; reproduction).
3. Create it with the `new_experiment` MCP tool (or `loupe new <name> --domain <domain>`), the name
   kebab-case and named for the question. It starts `active`.
4. Fill the README before the code, one or two sentences a section:
   - **Question**: comes out yes or no, or as a number.
   - **Observation**: what was seen, apart from what it is thought to mean.
   - **Hypotheses**: including the ones that compete with the user's.
   - **Baseline**: the nearest existing method, and the simplest thing that might already work.
   - **Test**: the conditions, the metric, the seeds. Correctness and behaviour metrics are named
     apart and never averaged.
   - **Stop if**: the result that would weaken the idea.
5. Write `run.py` from existing tools (transformers, nnsight, Inspect, TRL) and `loupe` where it
   has the piece. `Args` is the Launch form. Inside `start_run`: numbers with
   `mlflow.log_metrics`, per-item records as `raw/<condition>.jsonl` (one file per condition, an
   id field in every row) so the run page lines them up, a `report.md` for people. A paper's
   harness with its own pins runs in its own environment, not this one.
6. Run a small check here first (`launch` then `job`, or the app's Launch page), read it with
   `read-results`, then the real run, on a cluster if the model is large (`run-elsewhere`).
7. Write the Result (model, date, numbers with denominators) and Next. Set `status: answered`
   only when a real model's result answers the question.
