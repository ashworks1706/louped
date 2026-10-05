# Working in this research project

This is a louped project: each research question about a language model is an experiment under
`experiments/`, and louped runs it, records it and shows it. The person reads and judges results in
the app (`louped serve`, http://127.0.0.1:8000); you write experiments, launch them and read their
results.

## Tools

- `louped mcp`, registered in `.mcp.json`, drives the running app: `experiments`, `runs`, `run`,
  `samples`, `figures`, `compare` to read; `new_experiment`, `launch`, `job`, `export_job`,
  `import_result`, `push`, `pull` to act. Work started through it shows in the app. Start `louped serve` first.
  `ui_page`, `set_part`, `set_layout` and `set_preset` change what the app's pages show; the
  person Shift+clicks any part of a page and `ui_selection` gives you those parts with their
  data; `ui_show` points the person at parts, with a note. `cohort` reads a run's conditions on
  some items with paired intervals; `save_cohort` saves them for a run.py's `--cohort`.
- Skills in `.claude/skills/`: `new-experiment`, `read-results`, `run-elsewhere`, `write-report`,
  `add-plugin`, `change-ui`.
- The CLI does the same steps: `louped new`, `louped push`, `louped pull`, `louped --help`.
- Never ask for a Hugging Face token in chat. If push or pull says one is missing, ask the person
  to press Connect on Runs or run `louped push` in a terminal: both ask for it and keep it out of
  the project.

## The method

1. A question is one experiment: `experiments/<question>/README.md` opens with front matter
   (`domain`, `status`) and then Question, Observation, Hypotheses, Baseline, Test, Stop if, Run,
   Result, Next. Fill the README before the code.
2. `run.py` is the experiment's code: a tyro `Args` dataclass (the app's Launch form) and a
   `main` that runs inside `louped.tracking.start_run`, which records RunMeta (versions, commit,
   seed) with every result. Numbers go to `mlflow.log_metrics`; files to `mlflow.log_artifact`;
   per-item records as one JSONL file per condition in one folder, which the run page lines up
   item by item. Inspect evals go in `task.py`.
3. Compare conditions on the same items: fix the cohort from the baseline, report counts with
   their denominators, and a difference only with its paired interval (`compare`). Name the run
   ids you used.
4. Pin what moves numbers: the model's revision, the seed, greedy decoding unless sampling is the
   point.
5. Real runs on large models go to a cluster (`run-elsewhere`); this machine runs small checks.
6. Write the result in the README's Result (model, date, numbers) and the decision in Next, as
   `write-report` says: every number traced to a run, no claim past what was tested. Set
   `status: answered` when a real model's result answers the question.

## Where things are

| Path              | What                                                  |
| ----------------- | ----------------------------------------------------- |
| `louped.toml`      | the project's root and settings (domains, remote, theme) |
| `layout.json`     | what the app's pages show (`change-ui`); committed     |
| `experiments/`    | the questions; committed                              |
| `plugins/`        | the project's own pages, routes and tools; committed  |
| `.louped/`         | runs, eval logs, jobs, caches; gitignored, rebuildable |
