# Working in this research project

This is a loupe project: each research question about a language model is an experiment under
`experiments/`, and loupe runs it, records it and shows it. The person reads and judges results in
the app (`loupe serve`, http://127.0.0.1:8000); you write experiments, launch them and read their
results.

## Tools

- `loupe mcp`, registered in `.mcp.json`, drives the running app: `experiments`, `runs`, `run`,
  `samples`, `figures`, `compare` to read; `new_experiment`, `launch`, `job`, `export_job`,
  `import_result` to act. Work started through it shows in the app. Start `loupe serve` first.
- Skills in `.claude/skills/`: `new-experiment`, `read-results`, `run-elsewhere`.
- The CLI does the same steps: `loupe new`, `loupe import`, `loupe --help`.

## The method

1. A question is one experiment: `experiments/<question>/README.md` opens with front matter
   (`domain`, `status`) and then Question, Observation, Hypotheses, Baseline, Test, Stop if, Run,
   Result, Next. Fill the README before the code.
2. `run.py` is the experiment's code: a tyro `Args` dataclass (the app's Launch form) and a
   `main` that runs inside `loupe.tracking.start_run`, which records RunMeta (versions, commit,
   seed) with every result. Numbers go to `mlflow.log_metrics`; files to `mlflow.log_artifact`;
   per-item records as one JSONL file per condition in one folder, which the run page lines up
   item by item. Inspect evals go in `task.py`.
3. Compare conditions on the same items: fix the cohort from the baseline, report counts with
   their denominators, and a difference only with its paired interval (`compare`). Name the run
   ids you used.
4. Pin what moves numbers: the model's revision, the seed, greedy decoding unless sampling is the
   point.
5. Real runs on large models go to a cluster (`run-elsewhere`); this machine runs small checks.
6. Write the result in the README's Result (model, date, numbers) and the decision in Next; set
   `status: answered` when a real model's result answers the question.

## Where things are

| Path              | What                                                  |
| ----------------- | ----------------------------------------------------- |
| `loupe.toml`      | the project's root and settings (its domains)         |
| `experiments/`    | the questions; committed                              |
| `.loupe/`         | runs, eval logs, jobs, caches; gitignored, rebuildable |
