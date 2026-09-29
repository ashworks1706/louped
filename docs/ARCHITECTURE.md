# Architecture

## What loupe is

loupe lets you change a model (interventions, fine-tuning, prompts, adapters), prove what changed
(evals on both versions, sample by sample, with paired intervals and moved/held verdicts), and see
why (lens, patching, probes, SAE features, circuits), in one local app you launch and read
everything from.

It is built on existing free tools and writes only what joins them: one way to describe a change,
one provider that runs any change in an eval, one data format for results, and the UI over all of
it. A tool loupe needs runs inside it, as a library, or in an environment of its own when it pins
other versions. Nothing it does well is rewritten.

## The one idea: a change runs everywhere

```
policy = model + interventions + adapters + generation settings
```

The same policy runs in an Inspect eval (through the `loupe/` provider, agents with tools
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
| SAEs | SAELens | library; dashboards computed by `loupe features` |
| Attribution graphs | circuit-tracer | own environment through uv (`loupe circuit`); its viewer served on the Circuits page |
| Representation fine-tuning (LoReFT) | pyreft | own environment through uv (`loupe train reft`) |
| Probes | scikit-learn | library |
| Retrieval, reranking, NLI | bm25s, sentence-transformers | library |
| Tracking | MLflow on SQLite, Inspect logs | library |
| API and UI | FastAPI; Next.js static export, shadcn/ui, TanStack Query, nuqs, Recharts | |

Rejected: verifiers (pulls in hosted-API clients; TRL's environments cover it), vLLM, EasySteer and
cluster launchers (loupe stays on one machine and batches through its own provider),
TransformerLens (reimplements architectures, lags new models), Hydra (each tool keeps its native
config; scripts use tyro), W&B (its server is not free to self-host), a plugin registry (Inspect's
registries and Python entry points exist).

## Research domains

loupe is organised by research domain, not by the system that asks. A question is an experiment
in `experiments/`, named for the question. Nothing in `src/loupe` knows about any one system: a
system you study comes in as a model id, an OpenAI-compatible endpoint (`loupe.grid.endpoint`), an
agent endpoint that reports the tools it ran in a `trace` field on its reply (the `agent/`
provider), its regression cases as JSONL (`loupe.inspect_ext.cases`) or its logged model calls,
and its specifics stay in an experiment's options. The domains and their
experiments are listed in `apps/site/content/docs/domains.mdx`.

## Packages and layers

One distribution (`loupelab`), import name `loupe`, one extra per capability so an install carries
only what it uses. A package imports only packages below it; `import-linter` enforces the contract
in `pyproject.toml`.

```
experiments                              leaf, nothing imports it
cli
server                                   FastAPI over the stores; Playground; launching jobs
train | sweep | grid | features | circuits
                                         training recipes and sweeps; steering sweeps; condition
                                         grids; SAE dashboards; attribution graphs
stores | tracking | analysis | inspect_ext
                                         read Inspect logs and MLflow; start a run; lens, patching,
                                         probes, attention, SAE features as views; the loupe/
                                         provider, scorers, tasks
interventions                            steer, ablate, inject and heads specs; batched generation
vectors                                  directions as safetensors
models | data | retrieval                load a model, adapter banks, masked diffusion; training
                                         sets; search and its metrics
core                                     run metadata, paths
```

## Data

- Evals: Inspect `.eval` logs hold transcripts and per-sample scores.
- Everything else: an MLflow run with params, metrics and artifacts. Figures are JSON under
  `views/` in four shapes (heatmap, line, table, tokens; `loupe.analysis.views`); SAE dashboards are
  JSON under `features/`.
- Directions: one safetensors file each under `<LOUPE_HOME>/vectors`, provenance in the header,
  read without torch so `loupe serve` needs no interp extra.
- SAEs load through SAELens; loupe reads the residual at the SAE's hook with nnsight, so the model
  is never swapped for a TransformerLens one.
- Every run writes `RunMeta`: commit and dirty flag, package versions, seed.

## Server and UI

`apps/web` is a static Next.js export that `loupe serve` serves next to the API; there is no Node
server in production. The server owns no database and no auth; every route reads what another tool
wrote. Three things compute: the Playground (generate, which streams, and inspect, which returns a
prompt's views), launching jobs, and loading a model into the Playground. A job is an existing
command (an experiment script, `loupe train`, `loupe features`, `inspect eval`) in a subprocess,
one at a time, its output under `<home>/jobs`; each form is read from the command's own argument
parser. Launching and loading run code on this machine, so both are on only for a loopback server,
never with `--expose`.

Pages: Home, Experiments, Launch, Runs, Run, Feature, Compare, Vectors, Circuits, Playground.
Design rules are in `apps/web/AGENTS.md`. `apps/site` is the docs site; `deploy/app` is the
read-only public demo.

## Correctness traps the code must test

- Left padding: "last token" positions are per row after padding.
- bf16 steering: add in fp32, cast back; log the vector's norm relative to the residual's.
- Chat templates: log the rendered string; pin `enable_thinking` for Qwen3.
- Multi-turn protocols: support generated and forced earlier turns.
- Answer parsing: report the parse-failure rate as a metric.
