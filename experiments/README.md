# Experiments

One folder per research question, named for the question. Nothing outside this directory imports
anything in it, so an experiment can be abandoned by deleting its folder.

New on the Experiments page (or `loupe new <name> --domain <domain>`) creates the folder with a `README.md` (the question, what would answer
it, the result) and a `run.py` that writes its result under `.loupe/` rather than printing it.

When the same code appears in two experiments, it moves into `src/loupe`.
