# loupe: agent guide

loupe is a local testbed for research on LLM behavior and efficiency: each research question is an
experiment, filed under a domain on one of two axes (behavior and alignment, efficiency and
systems) or under the instrument checks. Read `docs/ARCHITECTURE.md` for the design and the tools
it runs, `docs/ROADMAP.md` for what is next.
Do not contradict them; propose an edit to the doc instead.

## Rules that decide most changes

- **Integrate, don't rewrite.** Before writing code, name the tool that already does it and run it
  inside loupe: as a library, or in its own environment when it pins other versions. Own code is
  the join between tools. A new dependency must be free and permissively licensed (MIT, Apache,
  BSD, OFL) and justified in the PR.
- **No speculative code.** No module, option or abstraction without a caller today.
- **Questions before infrastructure.** Code in `src/loupe` earns its place when an experiment needs
  it. A question is an experiment in `experiments/`, named for the question, its README opening
  with its domain and status (`DOMAINS` in `src/loupe/stores/experiments.py`). Nothing in
  `src/loupe` or an experiment's name is tied to one application: a system comes in as a model
  id, an OpenAI-compatible endpoint, an agent endpoint or logged calls.
- **Say what happened.** No silent fallbacks: raise, or print what was chosen. No fake paths in
  `src/loupe`; stand-ins belong in tests.
- **Reproducible numbers.** Anything that writes a result writes `loupe.core.RunMeta` next to it.
- **Local.** No step calls a hosted model; a judge, if one is needed, is a local model through the
  `loupe/` provider.

## Commands

`just` is the entrypoint; `just` alone lists recipes.

```
just bootstrap          first run: dependencies and git hooks
just check              the gate: Python (ruff, pyright, import-linter, pytest), web and site builds
just test-e2e           Playwright on the built UI; screenshots land in apps/web/test-results
just examples           the worked examples end to end on tiny offline models; CI runs it
just fmt                format everything
just serve              API and UI on :8000 (builds the UI first if needed)
just web                UI dev server on :3000
just site               docs site on :3001
just api-types          regenerate the UI's API types after changing a server route or model
```

A change is not done until `just check` passes.

## Layout

```
src/loupe/        the package (distribution loupelab); layers in docs/ARCHITECTURE.md
  core/           run metadata, paths
  models/         load a model, adapter banks, masked diffusion, tiny test models
  vectors/        directions as safetensors
  interventions/  steer, ablate, inject and heads specs; batched generation
  analysis/       lens, patching, probes, attention, projections, SAE features, as views
  inspect_ext/    the loupe/ and agent/ providers, scorers, tasks, regression cases
  data/           training sets from logged calls or a teacher
  retrieval/      search and its metrics
  train/          sft, dpo, grpo, classify, reft, sweeps, replayed tool environments
  stores/         read Inspect logs, MLflow, vectors, experiments/
  server/         the API, the Playground, launching jobs
  sweep.py grid.py features.py circuits.py cli.py
apps/web/         the UI; its AGENTS.md holds the design rules
apps/site/        the docs site
experiments/      one folder per research question, filed by domain; nothing imports it
deploy/app/       the read-only public demo
tests/            Python tests, CPU only
```

nnsight traces the source of the block it runs: keep trace bodies in files, use explicit loops
(not comprehensions) inside them, and touch modules in execution order. The UI talks to the server
over HTTP only.

## Branches and pull requests

`main` takes no direct pushes. Work on a branch, open a pull request, squash merge. Conventional
commit titles (`feat:`, `fix:`, `docs:`, `chore:`); release-please builds the changelog from them.
The one required check is `CI`. Never force-push to `main`, move a tag or publish a release unless
asked.

## Agent tooling

`.claude/skills/` holds the workflows (`check`, `new-experiment`, `roadmap`, `code-quality`, and
vendored debugging, TDD, verification and security skills). Run the `loupe-reviewer` agent before
opening a pull request and `web-reviewer` after any change under `apps/web`.
