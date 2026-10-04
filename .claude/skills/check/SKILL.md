---
name: check
description: Run louped's gate (just check), fix what fails, and report. Use before calling any change done.
---

1. Run `just check`. It runs `check-python` (ruff format, ruff check, pyright, import-linter,
   pytest) and `check-web` (prettier, eslint, tsc, static build).
2. For each failure, fix the cause, not the symptom:
   - Formatting: `just fmt`.
   - A layer violation from import-linter: move the code down a layer or invert the dependency.
     Never edit the contract to make it pass without updating `docs/ARCHITECTURE.md` in the same change.
   - A failing test: read it; change the code unless the test encodes something the change was
     meant to alter, and then say so.
3. If the change touches `apps/web`, also run `just test-e2e` and look at the screenshots in
   `apps/web/test-results/` (desktop and mobile). A page that passes but looks wrong is not done.
4. Rerun `just check` until it is green. Report what failed and what you changed.
