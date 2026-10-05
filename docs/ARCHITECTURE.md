# Architecture

## What louped is

louped is a local testbed for research on language models along two axes: behavior and alignment
(what models do and why) and efficiency and systems (what it costs to run them), plus instrument
checks that reproduce known results so both can be trusted. A research question is an experiment;
the app shows which questions are active, launches them and reads their results.

Every experiment uses one method: change a model (interventions, fine-tuning, prompts, adapters,
kernels), measure what changed (evals on both versions, sample by sample, with paired intervals
and moved/held verdicts), and explain it (lens, patching, probes, SAE features, circuits).

It is built on existing free tools and writes only what joins them: one way to describe a change,
one provider that runs any change in an eval, one data format for results, and the UI over all of
it. A tool louped needs runs inside it, as a library, or in an environment of its own when it pins
other versions. Nothing it does well is rewritten.

## The package and a project

louped is installed once (`pip install louped`: the library, the `louped` command, the API and
the UI, which the wheel carries as `louped/web`) and used in research projects, each its own
folder and repository. `louped init` makes one:

```
my-research/
  louped.toml          marks the root (commands find it from any subfolder) and lists its domains
  experiments/        the questions, written by the person and their agent; committed
  AGENTS.md, .mcp.json, .claude/skills/
                      the harness for the person's own coding agent
  .louped/             what louped writes: runs, logs, jobs, vendored harnesses; gitignored
```

What is written by hand is versioned; what louped writes can be deleted and rebuilt by running the
experiments. `louped.core.project` finds the root; `louped.core.paths` puts `.louped/` and
`experiments/` there unless `LOUPED_HOME` and `LOUPED_EXPERIMENTS` say otherwise. louped's own
repository is not a project: it holds the package and, under `src/louped/templates/`, what `init`
copies (also served to Claude Code as a plugin through `.claude-plugin/marketplace.json`).

A model with an architecture of its own (an engine's trained retrieval layers) is studied once it
ships PyTorch modeling code: `load(remote_code=True)`, opt-in, since it runs the repository's
code. An engine's runtime behaviour (retrieval during generation) is mirrored by `inject`'s hook
points and checked against the engine through its endpoint; louped does not instrument a Rust or
C++ forward pass.

louped has no agent of its own. The person's agent (Claude Code, Codex, Cursor) drives it through
`louped mcp` and follows the project's `AGENTS.md`; the person reads and judges in the UI.
`louped view <folder>` opens results that were made without louped, read-only, with no project.

## The one idea: a change runs everywhere

```
policy = model + interventions + adapters + generation settings
```

The same policy runs in an Inspect eval (through the `louped/` provider, agents with tools
included), a training run, the Playground and an analysis. Base, steered, ablated, fine-tuned and
prompted versions are therefore compared by one eval, one scorer and one view. A check is a plain
function, wrapped once as an Inspect scorer (`inspect_ext.as_scorer`) and once as a reward
(`train.rewards.as_reward`), so an eval becomes an RL environment without a rewrite.

## Tools

| Need | Tool | How it runs |
|---|---|---|
| Hooks, caching, patching, steering on Hugging Face models | nnsight | library |
| Evals, agents, sandboxes, benchmarks | Inspect, inspect_evals | library; Inspect View served at /inspect |
| SFT, DPO, GRPO, LoRA, prompt tuning, adapter merging | TRL, PEFT, unsloth | library |
| RL environments, verifiable tasks, answer checks | TRL, reasoning-gym, math-verify | library |
| SAEs | SAELens | library; dashboards computed by `louped features` |
| Attribution graphs | circuit-tracer | own environment through uv (`louped circuit`); its viewer served on the Circuits page |
| Representation fine-tuning (LoReFT) | pyreft | own environment through uv (`louped train reft`) |
| Probes | scikit-learn | library |
| Retrieval, reranking, NLI | bm25s, sentence-transformers | library |
| Tracking | MLflow on SQLite, Inspect logs | library |
| API and UI | FastAPI; Next.js static export, shadcn/ui, TanStack Query, nuqs, Recharts, Plotly (3D, animation; loaded when shown) | |

Rejected: verifiers (pulls in hosted-API clients; TRL's environments cover it), vLLM, EasySteer and
cluster launchers such as submitit (a job runs here through louped's own provider, or is exported as
a bundle whose job.sh the cluster's own scheduler runs and whose result comes back through the
remote or is imported),
TransformerLens (reimplements architectures, lags new models), Hydra (each tool keeps its native
config; scripts use tyro), W&B (its server is not free to self-host), a plugin registry or marketplace (Inspect's
registries and Python entry points exist; a project's own plugins/ folder is all louped reads,
see louped.core.plugins: routes, a command, MCP tools, and static pages shown at a sidebar entry
or as a tab on every run and experiment).

## Research axes and domains

louped is organised by research question, not by the system that asks or by the tool that answers.

| Axis | Domains |
|---|---|
| Behavior and alignment | mechanisms; sycophancy and honesty; steering and conditioning; agent behavior |
| Efficiency and systems | context and retrieval inside the model; inference cost and kernels; small and specialised models |
| Instrument checks | reproducing known results |

A question is an experiment in a project's `experiments/`, named for the question. Its README opens
with front matter naming its domain and status (active, parked, answered); the project's
`louped.toml` lists its domains and their axes, else `louped.stores.experiments.DEFAULT_DOMAINS`
does, and an experiment naming none of them is refused. Evaluation,
training, interventions and analysis are methods every domain uses, so they are packages in
`src/louped`, not domains.

Nothing in `src/louped` knows about any one system: a system you study comes in as a model id, an
OpenAI-compatible endpoint (`louped.grid.endpoint`), an agent endpoint that reports the tools it ran
in a `trace` field on its reply (the `agent/` provider), its regression cases as JSONL
(`louped.inspect_ext.cases`) or its logged model calls, and its specifics stay in an experiment's
options. The default domains, and how a project lists its own, are in `apps/site/content/docs/experiments.mdx`; what
goes in an experiment's folder, and how the app finds it, in `apps/site/content/docs/experiments.mdx`.

## Packages and layers

One distribution (`louped`), import name `louped`, one extra per capability so an install carries
only what it uses. A package imports only packages below it; `import-linter` enforces the contract
in `pyproject.toml`.

```
experiments                              leaf, in a project; nothing imports it
cli
server | agent | init                    FastAPI over the stores; Playground; launching jobs; the
                                         MCP server, an HTTP client of the API; louped init
check                                    what in the project's Markdown is not grounded
train | sweep | grid | sync | features | circuits | judge | bench | derive | sources
                                         training recipes and sweeps; steering sweeps; condition
                                         grids; SAE dashboards; attribution graphs; pairwise judging;
                                         serving cost; columns and figures from a run's files; the project's sources
stores | tracking | analysis | inspect_ext
                                         read Inspect logs and MLflow; start a run; lens, patching,
                                         probes, attention, SAE features as views; the louped/
                                         provider, scorers, tasks
interventions                            steer, ablate, inject and heads specs; batched generation
vectors                                  directions as safetensors
models | data | retrieval                load a model, adapter banks, masked diffusion; training
                                         sets; search and its metrics
core                                     run metadata, paths, the project and its plugins
```

## Data

- Evals: Inspect `.eval` logs hold transcripts and per-sample scores.
- Everything else: an MLflow run with params, metrics and artifacts. Figures are JSON under
  `views/` in seven kinds (heatmap, line, scatter, table, tokens, vega, plotly;
  `louped.analysis.views`); SAE dashboards are JSON under `features/`. `louped derive` and an
  agent's `add_view` add to a finished run: columns under `derived/`, figures under `views/`,
  each listed in its `louped.added` tag. An experiment's own figures are `experiments/<name>/views/`.
- Sources: `sources/` in the project (`louped.sources`): papers, docs, slides and notebooks listed
  in `sources/index.json` with key, origin URL and sha256; their text page by page in an FTS5
  index at `<home>/sources.db`, rebuilt from the files when one changes. Pins in
  `sources/pins.jsonl` (the quote as it stands on its page), checked against the page's
  text; the web app draws PDFs with pdf.js and renders `[@key pN]` in Markdown as citation chips.
  `louped.check` lists result numbers with no ref or citation beside them, citations without a
  pinned page, refs that do not resolve, and pins whose quote left its page.
- Refs (`louped.core.refs`) address evidence: `run:<id>/<path>#<item>`, `experiment:<name>/<path>`.
  A vega or plotly figure whose marks are items says so (`items`; plotly trace `ids`), and
  `louped.stores.trace` follows a mark's ref to the derive script and commit, the item's record
  in every file, and the run's commit (`GET /api/trace`, MCP `trace`).
- Judges: `judges/<name>.py` in the project, read without running for the list
  (`louped.core.judges`) and imported only by a judging job. Eval tasks are Inspect tasks: the
  project's `@task` functions and inspect_evals' `eval.yaml` metadata (`louped.stores.catalog`).
- Directions: one safetensors file each under `<LOUPED_HOME>/vectors`, provenance in the header,
  read without torch so `louped serve` needs no interp extra.
- SAEs load through SAELens; louped reads the residual at the SAE's hook with nnsight, so the model
  is never swapped for a TransformerLens one.
- Every run writes `RunMeta`: commit and dirty flag, package versions, seed.
- Every run started by `start_run` also carries the machine while it was open, as MLflow's
  `system/` metrics sampled every 2 s: GPU power, utilisation and memory (NVML, which sees every
  process on a GPU), CPU and RAM. The UI keeps them out of a run's results and shows them, with
  the GPU energy, under Hardware.

## Server and UI

`apps/web` is a static Next.js export that `louped serve` serves next to the API; there is no Node
server in production. The server owns no database and no auth; every route reads what another tool
wrote. Three things compute: the Playground (generate, which streams and continues a conversation
for a follow-up; inspect, which returns a prompt's views; patch, residual or head patching between a
clean and a corrupt prompt; dose, a saved direction swept over strengths at the next token; speed,
time to first token, decode throughput and peak memory, base and changed), launching jobs, and
loading a model into the Playground. A job is an existing command (an experiment script,
`louped train`, `louped grid`, `louped new`, `louped features`, `inspect eval`) in a subprocess, one at
a time, its output under `<home>/jobs`; or exported (server/remote.py) as a bundle whose job.sh
runs it on Sol, a Slurm cluster or a VM (one file that clones the project when it is a pushed git
commit), and whose results come back through the remote or as an archive imported into the stores;
each form is read from the command's own argument parser. Launching and loading run code on this machine, so both are on only for a loopback server,
never with `--expose`.

Runs move between machines as bundles (`louped.sync`): a folder laid out as a louped home (Inspect
logs, an MLflow store with its artifacts, result.json). `louped push` writes one per push into the
remote, any fsspec URL (`remote` in louped.toml); `louped pull` and `louped import` add a bundle's
runs to the stores, skipping runs already there. An `hf://buckets/` remote is made, private, on
the first push; its token is huggingface_hub's own (`hf auth login`, HF_TOKEN), which the app's
Connect dialog and the CLI's first push ask for and never write into the project. `louped publish` (server/publish.py) writes the UI
with every GET answer its pages ask for as static files, for any static host.

`louped mcp` is a stdio MCP server for coding agents. It imports nothing from the server: it calls
the same HTTP API the UI does, so an agent's jobs share the queue and the `--expose` guard, and show
on the Runs page.

Pages: a top bar of sections over a sidebar of the section's pages, which folds to icons. The
workspace: Home, Runs (jobs with their progress, then every run), Compare, Launch, with Run and Job
detail. Each research domain lives under its own path: `/behavior/` Overview, Experiments, Probe
(reply, inspect, patch, dose), Vectors, Circuits, Feature; `/efficiency/` Overview, Experiments,
Benchmark (speed, reply), Training. An experiment's page is under its domain's path. Probe and
Benchmark are one playground with different tools. Every technical term has a ? from
`apps/web/src/lib/glossary.ts`.

Home, a run's page and an experiment's page are data (server/ui.py): regions (`run.tabs`,
`run.overview`, ...) of blocks from a fixed catalog, read from an experiment's `layout.json` over
the project's over a preset over the default, each file checked before it is used. The person's
agent changes them with `set_layout`. Inside the blocks every part (card, row, cell, field,
column, control) has an address (server/parts.py lists the kinds), and a layout's `parts` change
them by address: hidden, label, about, note, order, a control's default. Shift+click in the app
picks parts, with what each stands for (an item's records, a condition's numbers), for the agent's
`ui_selection`; the agent's `ui_show` opens a page and points at parts with a note, and hears back
which were missing. A block the catalog lacks is a plugin page, drawn with the kit at `/kit/`
(louped.css, louped.js) so it reads as the app's own. louped.toml's `[theme]` sets token values
only. Picked item rows are a cohort: `stores/items.py` reads a run's conditions on them, with the
paired bootstrap interval `compare` uses, and `core/cohorts.py` saves them in the experiment
(`cohorts/<name>.json`) for a run.py's `--cohort` (`louped.tracking.cohort_ids`).
Design rules are in `apps/web/AGENTS.md`. `apps/site` is the docs site.

## Correctness traps the code must test

- Left padding: "last token" positions are per row after padding.
- bf16 steering: add in fp32, cast back; log the vector's norm relative to the residual's.
- Chat templates: log the rendered string; pin `enable_thinking` for Qwen3.
- Multi-turn protocols: support generated and forced earlier turns.
- Answer parsing: report the parse-failure rate as a metric.
