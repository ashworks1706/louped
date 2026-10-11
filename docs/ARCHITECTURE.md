# Architecture

## What louped is

louped is a local workbench for research on language models. The research has two axes:

- behavior and alignment (what models do and why)
- efficiency and systems (what it costs to run them)

Instrument checks reproduce known results, so the results on both axes can be trusted. A research
question is an experiment. The app shows which questions are active, launches them and reads their
results.

Every experiment uses one method:

1. Change a model (interventions, fine-tuning, prompts, adapters, kernels).
2. Measure what changed (evals on both versions, sample by sample, with paired intervals and
   moved/held verdicts).
3. Explain it (lens, patching, probes, SAE features, circuits).

It is built on existing free tools and writes only what joins them:

- one way to describe a change
- one provider that runs any change in an eval
- one data format for results
- the UI over all of it

A tool louped needs runs inside it as a library. When the tool pins other versions, it runs in an
environment of its own. louped does not rewrite what a tool already does well.

## The package and a project

louped is installed once (`pip install louped`). The install gives the library, the `louped`
command, the API and the UI, which the wheel carries as `louped/web`. You use it in research
projects; each project is its own folder and repository. `louped init` makes one:

```
my-research/
  louped.toml          marks the root (commands find it from any subfolder) and lists its domains
  experiments/        the questions, written by the person and their agent; committed
  AGENTS.md, .mcp.json, .claude/skills/, .claude/settings.json
                      the harness for the person's own coding agent
  .louped/             what louped writes: runs, logs, jobs, vendored harnesses; gitignored
```

What is written by hand is versioned. What louped writes can be deleted and rebuilt by running the
experiments. `louped.core.project` finds the root. `louped.core.paths` puts `.louped/` and
`experiments/` there, unless `LOUPED_HOME` and `LOUPED_EXPERIMENTS` set other paths.

louped's own repository is not a project. It holds the package and, under `src/louped/templates/`,
the files that `init` copies. These files are also served to Claude Code as a plugin through
`.claude-plugin/marketplace.json`.

louped can study a model with an architecture of its own (for example, an engine's trained
retrieval layers) when the model ships PyTorch modeling code. Use `load(remote_code=True)`. It is
opt-in, because it runs the repository's code. `inject`'s hook points mirror an engine's runtime
behavior (retrieval during generation), and louped checks them against the engine through its
endpoint. louped does not instrument a Rust or C++ forward pass.

louped has no agent of its own. The person's agent (Claude Code, Codex, Cursor) drives it through
`louped mcp` and follows the project's `AGENTS.md`. The person reads and judges in the UI.
`louped view <folder>` opens results that were made without louped. It opens them read-only, with
no project.

## The one idea: a change runs everywhere

```
policy = model + interventions + adapters + generation settings
```

The same policy runs in:

- an Inspect eval (through the `louped/` provider, agents with tools included)
- a training run
- the Probe and Benchmark tools
- an analysis

Thus one eval, one scorer and one view compare the base, steered, ablated, fine-tuned and prompted
versions. A check is a plain function. It is wrapped once as an Inspect scorer
(`inspect_ext.as_scorer`) and once as a reward (`train.rewards.as_reward`). Thus an eval becomes an
RL environment without a rewrite.

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
| API and UI | FastAPI; Next.js static export, shadcn/ui, TanStack Query, nuqs, Recharts, Plotly (3D, animation; loaded when shown), dagre (a board's diagrams) | |

Rejected:

| Tool | Why rejected |
|---|---|
| verifiers | It pulls in hosted-API clients. TRL's environments cover it. |
| vLLM, EasySteer, cluster launchers such as submitit | A job runs here through louped's own provider. Or it is exported as a bundle: the cluster's own scheduler runs its job.sh, and its result comes back through the remote or is imported. |
| TransformerLens | It reimplements architectures and lags new models. |
| Hydra | Each tool keeps its native config. Scripts use tyro. |
| W&B | Its server is not free to self-host. |
| A plugin registry or marketplace | Inspect's registries and Python entry points exist. louped reads only a project's own plugins/ folder (see louped.core.plugins): routes, a command, MCP tools, and static pages shown at a sidebar entry or as a tab on every run and experiment. |

## Research axes and domains

louped is organized by research question, not by the system that asks or by the tool that answers.

| Axis | Domains |
|---|---|
| Behavior and alignment | mechanisms; sycophancy and honesty; steering and conditioning; agent behavior |
| Efficiency and systems | context and retrieval inside the model; inference cost and kernels; small and specialized models |
| Instrument checks | reproducing known results |

A question is an experiment in a project's `experiments/`, named for the question. Its README opens
with front matter that names its domain and status (active, parked, answered). The project's
`louped.toml` lists its domains and their axes. If it does not, `louped.stores.experiments.DEFAULT_DOMAINS`
lists them. louped refuses an experiment that names none of them. Evaluation, training,
interventions and analysis are methods every domain uses. Thus they are packages in `src/louped`,
not domains.

Nothing in `src/louped` knows about any one system. A system you study comes in as one of these:

- a model id
- an OpenAI-compatible endpoint (`louped.grid.endpoint`)
- an agent endpoint that reports the tools it ran in a `trace` field on its reply (the `agent/`
  provider)
- its regression cases as JSONL (`louped.inspect_ext.cases`)
- its logged model calls

Its specifics stay in an experiment's options. `apps/site/content/docs/experiments.mdx` gives the
default domains and how a project lists its own. The same page tells what goes in an experiment's
folder and how the app finds it.

## Packages and layers

There is one distribution (`louped`), with the import name `louped`. `pip install louped` gives
the app, evals, run tracking, model loading and the agent's tools; extras add training, RL,
retrieval and SAEs. A package imports only packages below it.
`import-linter` enforces the contract in `pyproject.toml`.

```
experiments                              leaf, in a project; nothing imports it
cli
server | agent | init | picks           FastAPI over the stores; Probe and Benchmark; jobs; the
                                         MCP server, an HTTP client of the API; louped init; the
                                         prompt hook that hands the agent the person's picks
check                                    what in the project's write-ups is not grounded
reports                                  reports/: decks, documents, exported figures
train | sweep | grid | sync | features | circuits | judge | bench | derive | sources | notebooks
                                         training recipes and sweeps; steering sweeps; condition
                                         grids; SAE dashboards; attribution graphs; pairwise judging;
                                         serving cost; columns and figures from a run's files; the
                                         project's sources; notebooks run by papermill
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
- Sources: `sources/` in the project (`louped.sources`). It holds papers, docs, slides and
  notebooks, listed in `sources/index.json` with key, origin URL and sha256. Their text is stored
  page by page in an FTS5 index at `<home>/sources.db`. The index is rebuilt from the files when
  one changes. Pins are in `sources/pins.jsonl` (the quote as it stands on its page), checked
  against the page's text. The web app draws PDFs with pdf.js and renders `[@key pN]` in Markdown
  as citation chips.
  `louped.reports` lists reports/. It previews decks and documents through LibreOffice when
  installed. It exports Vega-Lite (vl-convert) and Plotly (Kaleido, with Chrome) figures with a
  `<file>.refs.json` sidecar that holds the ref and its trace. The same drawing gives the agent a
  figure as a PNG before the person sees it (`POST /api/views/preview`, MCP `preview_view`). It files each report under the
  experiment it reports on, and resolves the live refs in Markdown (`{{run:<id> <metric>}}`, a
  figure's ref) for the app's renderer (`GET /api/live`), so a write-up's numbers are read from
  its runs. `louped.core.documents` reads PDFs,
  decks, documents and notebooks for both. It draws a notebook as HTML (nbconvert) for a frame
  with no scripts.
- Notebooks: `louped.notebooks` runs an experiment's `.ipynb` with papermill inside a run; the
  cell tagged `parameters` is the launch form, and the run keeps `notebook/<name>.ipynb`. The
  kernel finds its run through `MLFLOW_RUN_ID`, so cells log to it.
  `louped.check` lists result numbers with no ref or citation beside them, citations without a
  pinned page, refs that do not resolve, and pins whose quote left its page.
- Refs (`louped.core.refs`) address evidence: `run:<id>/<path>#<item>`, `experiment:<name>/<path>`.
  A vega or plotly figure whose marks are items says so (`items`; plotly trace `ids`).
  `louped.stores.trace` follows a mark's ref to the derive script and commit, the item's record
  in every file, and the run's commit (`GET /api/trace`, MCP `trace`).
- Judges: `judges/<name>.py` in the project, read without running for the list
  (`louped.core.judges`) and imported only by a judging job. Eval tasks are Inspect tasks: the
  project's `@task` functions and inspect_evals' `eval.yaml` metadata (`louped.stores.catalog`).
- Directions: one safetensors file each under `<LOUPED_HOME>/vectors`, provenance in the header,
  read without torch so `louped serve` starts without importing it.
- SAEs load through SAELens; louped reads the residual at the SAE's hook with nnsight, so the model
  is never swapped for a TransformerLens one.
- Every run writes `RunMeta`: commit and dirty flag, package versions, seed.
- Every run started by `start_run` also records the machine while the run was open. It records
  MLflow's `system/` metrics, sampled every 2 s: GPU power, utilization and memory (NVML, which
  sees every process on a GPU), CPU and RAM. The UI keeps them out of a run's results. It shows
  them, with the GPU energy, under Hardware.

## Server and UI

`apps/web` is a static Next.js export that `louped serve` serves next to the API; there is no Node
server in production. The server owns no database and no auth.
Every route reads what another tool wrote.

Three parts compute: the Probe and Benchmark tools, job launch, and model load.

- The tools (server/playground.py, behind the Probe and Benchmark pages):
  - generate streams a reply and continues a conversation.
  - inspect returns a prompt's views.
  - patch patches the residual stream or heads between a clean and a corrupt prompt.
  - dose sweeps a saved direction over strengths at the next token.
  - speed measures time to first token, decode throughput and peak memory, base and changed.
- A job is an existing command in a subprocess: an experiment script or notebook, `louped train`,
  `louped grid`, `louped new`, `louped features` or `inspect eval`. Jobs run one at a time. Each job
  writes its output to `<home>/jobs`. A job's form is read from the command's own argument parser.
- A job can also be exported (server/remote.py) as a bundle. Its job.sh runs it on Sol, another
  Slurm cluster or a VM. When the project is a pushed git commit, the bundle is one file that
  clones it. The results come back through the remote, or as an archive that is imported.
- A job can also be submitted (server/submit.py) to a cluster that louped.toml names. louped
  copies the export there over ssh and starts it with sbatch (`louped.clusters`, every call with a
  timeout). While the server runs, it follows the job with sacct and brings the result back.
  `--after` chains jobs on the cluster with Slurm's afterok.
- An experiment's README can declare a gate (stores/gates.py): requirements on the newest
  finished run of one launch. Launch, export and submit refuse the launches it guards until it
  passes. `louped gate` checks it, also as a chain's step on the cluster.

Launching and loading run code on this machine. Thus both are on only for a loopback server, never
with `--expose`.

Runs move between machines as bundles (`louped.sync`). A bundle is a folder laid out as a louped
home (Inspect logs, an MLflow store with its artifacts, result.json). `louped push` writes one
bundle per push into the remote. The remote is any fsspec URL (`remote` in louped.toml).
`louped pull` and `louped import` add a bundle's runs to the stores, and skip runs already there.

The first push makes an `hf://buckets/` remote, private. Its token is huggingface_hub's own
(`hf auth login`, HF_TOKEN). The app's Connect dialog and the CLI's first push ask for it and never
write it into the project. `louped publish` (server/publish.py) writes the UI as static files, with
every GET answer its pages ask for, for any static host.

`louped mcp` is a stdio MCP server for coding agents. It imports nothing from the server. It calls
the same HTTP API the UI does. Thus an agent's jobs share the queue and the `--expose` guard, and
show on the Runs page. `louped picks --hook`, a Claude Code prompt hook, reads the same API: it adds
the parts the person Shift+clicked to their next message, and marks them read for the app's tray.

Pages: a top bar of sections is over a sidebar of the section's pages. The sidebar folds to icons.

| Section | Pages |
|---|---|
| Workspace | Home, Runs (jobs with their progress, then every run), Compare, Launch, Sources and Reports, with Run, Job, Source and Report detail |
| `/behavior/` | Overview, Experiments, Probe (reply, inspect, patch, dose), Vectors, Circuits, Feature |
| `/efficiency/` | Overview, Experiments, Benchmark (speed, reply), Training |

Each research domain lives under its own path. An experiment's page is under its domain's path.
Probe and Benchmark are one set of tools (server/playground.py); each page shows its own. Every
technical term has a ? from `apps/web/src/lib/glossary.ts`.

Home, a run's page and an experiment's page are data (server/ui.py). They are regions
(`run.tabs`, `run.overview`, ...) of blocks from a fixed catalog. The layout is read from an
experiment's `layout.json` over the project's over a preset over the default. Each file is checked
before it is used. The person's agent changes them with `set_layout`.

Inside the blocks every part (card, row, cell, field, column, control) has an address
(server/parts.py lists the kinds). A layout's `parts` change them by address: hidden, label,
about, note, order, a control's default. Shift+click in the app picks parts for the agent's
`ui_selection`, with what each part stands for (an item's records, a condition's numbers). The
agent's `ui_show` opens a page and points at parts with a note. It hears back which parts were
missing.

A block the catalog lacks is a plugin page. It is drawn with the kit at `/kit/` (louped.css,
louped.js), so it reads as the app's own. louped.toml's `[theme]` sets token values only.

Picked item rows are a cohort. `stores/items.py` reads a run's conditions on them, with the
paired bootstrap interval `compare` uses. `core/cohorts.py` saves them in the experiment
(`cohorts/<name>.json`) for a run.py's `--cohort` (`louped.tracking.cohort_ids`).
Design rules are in `apps/web/AGENTS.md`. `apps/site` is the docs site.

## Correctness traps the code must test

- Left padding: "last token" positions are per row after padding.
- bf16 steering: add in fp32, cast back; log the vector's norm relative to the residual's.
- Chat templates: log the rendered string; pin `enable_thinking` for Qwen3.
- Multi-turn protocols: support generated and forced earlier turns.
- Answer parsing: report the parse-failure rate as a metric.
