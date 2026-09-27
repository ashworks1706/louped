# loupe: agent guide

A research testbed for looking inside language models. loupe is **glue, not a framework**: nnsight
does interpretability, Inspect does evals and agents, TRL does training, verifiers does RL
environments, vLLM does fast generation, MLflow does tracking. loupe gives them one model, one
intervention spec and one data format, and a UI over all of it. The UI is the product.

Read `docs/ARCHITECTURE.md` for the layers and the design, `docs/ROADMAP.md` for what is built in
what order. Do not contradict them; propose an edit to the doc instead.

## Rules that decide most changes

- **Prebuilt first.** Before writing code, name the existing tool that does it. Own code is only
  the glue between tools. A new dependency must be free and permissively licensed (MIT, Apache,
  BSD, OFL) and justified in the PR.
- **No bloat.** No module, option or abstraction without a caller today. Python stays under ~3k
  lines, the UI under ~6k lines of our own TSX.
- **Reproducible numbers.** Anything that writes a result writes `loupe.core.RunMeta` next to it.
- **A UI page is done only when it renders a real experiment's data**, not only fixtures.

## Commands

`just` is the entrypoint; `just` alone lists recipes.

```
just bootstrap          first run: dependencies and git hooks
just check              the gate: check-python and check-web. CI and the pre-push hook run it
just check-python       ruff format, ruff check, pyright, import-linter, pytest
just check-web          prettier, eslint, tsc, static build
just test-e2e           Playwright on the built UI; screenshots land in apps/web/test-results
just fmt                format everything
just serve              API on :8000, serving the built UI
just web                UI dev server on :3000
just new-experiment X   scaffold experiments/X/
just lock               re-resolve uv.lock
just api-types          regenerate the UI's API types after changing a server route or model
```

A change is not done until `just check` passes.

## Layout

```
src/loupe/       the Python package (distribution name: loupelab)
  core/          run metadata, paths, the direction header
  models/        load a model into nnsight; a tiny offline Qwen2 for tests
  vectors/       directions as safetensors under <home>/vectors
  interventions/ Steer and Ablate specs, compiled to per-layer edits; batched generation
  analysis/      activations, logit lens, patching; results as UI views (heatmap, line, table)
  inspect_ext/   the loupe/ Inspect model provider and shared scorers
  data/          training sets from product traces: export, redact, verify, review, curate
  train/         post-training recipes (sft) on TRL and PEFT, logged to MLflow
  tracking/      start an MLflow run the UI can read
  stores/        read-only views over Inspect logs, MLflow, views/, vectors and experiments/
  server/        FastAPI over the stores, plus the Playground
  cli.py         the loupe command
apps/web/        the UI: Next.js static export, shadcn/ui. Its own AGENTS.md holds the design rules
experiments/     one folder per research question; nothing imports it
tests/           Python tests, CPU only
docs/            ARCHITECTURE.md, ROADMAP.md, decisions/
```

## The dependency rule

A package imports only packages below it. `import-linter` enforces this in `just check`; the
contract is in `pyproject.toml`. New layers are added there in the position ARCHITECTURE.md gives.

```
cli
server
train
stores | tracking | analysis | inspect_ext
interventions
vectors
models | data
core
```

Everything runs locally with no API keys: models come from the Hugging Face Hub or a path, the
stores are files under LOUPE_HOME, and no step calls a hosted model. Keep it that way; a model
judge, if one is ever needed, is a local model through the loupe/ provider or vLLM.

nnsight traces the source of the block it runs: keep trace bodies in files, use explicit loops
(not comprehensions) inside them, and touch modules in execution order.

The UI talks to the server over HTTP only.

## Branches and pull requests

`main` takes no direct pushes. Work on a branch, open a pull request, squash merge. Conventional
commit titles (`feat:`, `fix:`, `docs:`, `chore:`), because release-please builds the changelog and
the version from them. The one required check is `CI`. Never force-push to `main`, move a tag or
publish a release unless asked.
