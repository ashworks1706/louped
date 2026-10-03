# Experiments

One folder per research question, named for the question. Nothing outside this directory imports
anything in it, so an experiment can be abandoned by deleting its folder.

| Domain | Experiment |
| --- | --- |
| Behavior › Sycophancy and honesty | `rational-updating-baseline`: Experiment 1A, the unmitigated baseline of the rational-updating paper |
| Efficiency | none yet |

New on the Experiments page (or `loupe new <name> --domain <domain>`) creates the folder with a
`README.md` (the question, what would answer it, the result) and a `run.py` that launches from the
app. What else goes in a folder (Inspect tasks, figures, training and grid configs) and how the app
finds it is in `apps/site/content/docs/experiments.mdx`.

When the same code appears in two experiments, it moves into `src/loupe`.
