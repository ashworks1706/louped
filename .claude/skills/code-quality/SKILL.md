---
name: code-quality
description: Refactoring and cleanup pass over louped - dead code, wrappers that add nothing over the library, speculative options, duplicated glue. Quality only, not bug hunting. User-invoked.
---

# code-quality

A cleanup pass over code that already works. Not a bug hunt; use `/systematic-debugging` for that.

Behaviour must not change. If you find a bug, say so and stop; do not fold a fix into a refactor.

## What to look for

**Own code the library already does.** louped is glue. A helper that re-implements something
nnsight, Inspect, TRL, MLflow or TanStack already provides goes; call the library.

**Dead code.** Modules nothing imports, options nothing sets, parameters every caller passes the
same value for, exports nothing reads, dependencies nothing imports (`uvx vulture src/louped`
helps). Delete it; git remembers. Name the deletion in the commit message.

**Speculation.** An abstraction with one implementation and no second in the roadmap, a config key
for a case no experiment has. Inline it.

**Duplication across experiments.** The same code in two `experiments/*/run.py` belongs in
`src/louped` with a test (see `/new-experiment`).

**Silent fallbacks.** A fallback that says nothing hides a misconfiguration. Either raise, or
print what was chosen.

## What not to do

- Do not rename for taste, reformat unrelated code, or change a CLI command, API route or file
  format without saying so.
- Do not add a layer or an abstraction to make code "cleaner".

## Finish

`just check` and `just test-e2e` must pass. Report what you removed and
why.
