# louped: agent guide

louped is a local testbed for research on LLM behavior and efficiency: each research question is an
experiment, filed under a domain on one of two axes (behavior and alignment, efficiency and
systems) or under the instrument checks. Read `docs/ARCHITECTURE.md` for the design and the tools
it runs, `docs/ROADMAP.md` for what is next.
Do not contradict them; propose an edit to the doc instead.

## Rules that decide most changes

- **Integrate, don't rewrite.** Before writing code, name the tool that already does it and run it
  inside louped: as a library, or in its own environment when it pins other versions. Own code is
  the join between tools. A new dependency must be free and permissively licensed (MIT, Apache,
  BSD, OFL) and justified in the PR.
- **No speculative code.** No module, option or abstraction without a caller today.
- **Questions before infrastructure.** Code in `src/louped` earns its place when an experiment needs
  it. A question is an experiment in a research project (`louped init`, its own repository), not in
  this one: `experiments/<name>/`, its README opening with its domain and status (the project's
  `louped.toml`, else `DEFAULT_DOMAINS` in `src/louped/stores/experiments.py`). Nothing in
  `src/louped` or an experiment's name is tied to one application: a system comes in as a model
  id, an OpenAI-compatible endpoint, an agent endpoint or logged calls.
- **Say what happened.** No silent fallbacks: raise, or print what was chosen. No fake paths in
  `src/louped`; stand-ins belong in tests.
- **Reproducible numbers.** Anything that writes a result writes `louped.core.RunMeta` next to it.
- **Local.** No step calls a hosted model; a judge, if one is needed, is a local model through the
  `louped/` provider.

## Commands

`just` is the entrypoint; `just` alone lists recipes.

```
just bootstrap          first run: dependencies and git hooks
just check              the gate: Python (ruff, pyright, import-linter, pytest), web and site builds
just test-e2e           Playwright on the built UI; screenshots land in apps/web/test-results
just fmt                format everything
just serve              API and UI on :8000 (builds the UI first if needed)
just web                UI dev server on :3000
just site               docs site on :3001
just api-types          regenerate the UI's API types after changing a server route or model
```

A change is not done until `just check` passes.

## Layout

```
src/louped/        the package (distribution louped); layers in docs/ARCHITECTURE.md
  core/           run metadata, paths
  models/         load a model, adapter banks, masked diffusion, tiny test models
  vectors/        directions as safetensors
  interventions/  steer, ablate, inject and heads specs; batched generation
  analysis/       lens, patching, probes, attention, projections, SAE features, as views
  inspect_ext/    the louped/ and agent/ providers, scorers, tasks, regression cases
  data/           training sets from logged calls or a teacher
  retrieval/      search and its metrics
  train/          sft, dpo, grpo, classify, reft, sweeps, replayed tool environments
  stores/         read Inspect logs, MLflow, vectors, experiments/
  server/         the API, the Playground, launching jobs
  agent.py        the MCP server coding agents drive louped through
  sweep.py grid.py features.py circuits.py cli.py
  templates/      what `louped init` copies: the project files, the agent's skills and MCP config
                  (also the Claude Code plugin, listed in .claude-plugin/), the example experiment
  init.py         `louped init`
apps/web/         the UI; its AGENTS.md holds the design rules
apps/site/        the docs site
hatch_build.py    puts the built UI in the wheel as louped/web
tests/            Python tests, CPU only
```

## Where a change goes

| To add                     | Write                                                                    |
| -------------------------- | ------------------------------------------------------------------------ |
| A research question        | in a research project: `louped new <name> --domain <domain>`, then its README and `run.py` |
| An eval                    | Inspect `@task`s in `experiments/<name>/task.py`                           |
| A figure                   | a view from `louped.analysis.views`, logged with `log_json` under `views/` |
| A chart no kind draws      | `views.vega(title, spec)`: any Vega-Lite spec with its data inline, no change to louped |
| A project's own page, routes, command or agent tools | its `plugins/<name>/` (`louped.core.plugins`), no change to louped |
| A number                   | `mlflow.log_metrics` inside `louped.tracking.start_run`                    |
| A training run or a grid   | `experiments/<name>/*.yaml` starting `# louped train <recipe>` or `# louped grid` |
| A paper's own harness      | a pinned clone under `.louped/vendor/`, run in its own venv ("Someone else's code" in `apps/site/content/docs/experiments.mdx`) |
| What a new project gets    | `src/louped/templates/`: project files, agent skills, the example experiment |
| A domain                   | `[domains.<key>]` in the project's `louped.toml` ("Domains" in `apps/site/content/docs/experiments.mdx`) |
| A view kind the UI lacks   | `louped.analysis.views`, `View` in `stores/types.py`, a renderer in `apps/web/src/components/run-views.tsx`, `just api-types` |

The app finds each of these by convention: no registration. `apps/site/content/docs/experiments.mdx`
has the details.

nnsight traces the source of the block it runs: keep trace bodies in files, use explicit loops
(not comprehensions) inside them, and touch modules in execution order. The UI talks to the server
over HTTP only.

## Branches and pull requests

`main` takes no direct pushes. Work on a branch, open a pull request, squash merge. Conventional
commit titles (`feat:`, `fix:`, `docs:`, `chore:`); release-please builds the changelog from them.
The one required check is `CI`. Never force-push to `main`, move a tag or publish a release unless
asked.

## Agent tooling

`.claude/skills/` holds the workflows for developing louped (`check`, `roadmap`, `code-quality`, and
vendored debugging, TDD, verification and security skills). Run the `louped-reviewer` agent before
opening a pull request and `web-reviewer` after any change under `apps/web`.

`.mcp.json` registers `louped mcp`, which drives a running `louped serve`: read experiments, runs,
figures and samples, compare runs, and launch jobs through the app's queue. Prefer it to the CLI
for running experiments, so the work shows in the app.
