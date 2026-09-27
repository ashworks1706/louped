# Architecture

## What loupe is

A testbed for research on language models, from activations to agents, with a UI as its main
surface. Every capability is delegated to an existing free tool; loupe owns only the glue that
makes them share one model, one intervention spec and one data format.

## The tools it composes

| Need | Tool |
|---|---|
| Hooks, caching, patching, steering on real HF models | nnsight |
| SAEs; lens; attribution graphs | SAELens; tuned-lens; circuit-tracer |
| Linear probes | scikit-learn |
| Evals, multi-turn, agents, coding sandboxes | Inspect AI + inspect_evals |
| Standard benchmarks | lm-evaluation-harness |
| SFT, DPO, GRPO, LoRA; ReFT | TRL, PEFT, unsloth; pyreft |
| RL environments | verifiers (LLM), gymnasium (classic) |
| Fast generation | vLLM |
| Tracking | MLflow (self-hosted) and Inspect logs |
| Cluster and cloud | submitit (Slurm), SkyPilot |
| UI | Next.js static export, shadcn/ui, Tailwind, Geist, cmdk, TanStack Query, nuqs, Recharts |
| API | FastAPI |

Rejected: TransformerLens (reimplements architectures, lags new models), Hydra (each tool keeps its
native config; our scripts use tyro), W&B (server not self-hostable for free), a custom plugin
registry (Inspect's registries and Python entry points already exist).

## The one idea: a Policy runs everywhere

```
Policy = model + [interventions] + generation params
```

The same Policy is valid in an Inspect eval (through a loupe model provider), a TRL or verifiers
training run, the UI Playground, and an activation analysis. "Base", "base + steering", "base +
ablation" and "LoRA checkpoint" are therefore compared by one eval, one scorer and one UI view.
A task's scorer is a plain function wrapped once as an Inspect scorer and once as a reward, so an
eval becomes an RL environment without a rewrite.

## Packages and layers

One distribution (`loupelab`), import name `loupe`, one extra per capability so an install carries
only what it uses. A package imports only packages below it; `import-linter` enforces it.

```
experiments                      leaf, nothing imports it
cli
server                           FastAPI, read-only over the stores; Playground generation
train                            sft on TRL/PEFT or Unsloth, logged as MLflow training runs
stores | tracking | analysis     views over Inspect logs and MLflow; start an MLflow run;
  | inspect_ext                  lens, patching, probes, attention, SAE features as UI views;
                                 loupe/ provider and scorers
interventions                    Steer and Ablate specs on nnsight, batched generation
vectors                          directions as safetensors
models | data                    load a model into nnsight; training sets from product traces
core                             run metadata, paths
```

Today everything from `core` to `cli` exists; `rl_ext` (scorer to reward) joins `inspect_ext` in v0.5. Each phase adds its layers here and in the contract in
`pyproject.toml`.

## Data

- Evals: Inspect `.eval` logs are the source of truth for transcripts and per-sample scores.
- Everything else: an MLflow run with params, metrics and artifacts. Figures are data, not images:
  JSON under `views/` in one of three shapes (heatmap, line, table, `loupe.analysis.views`) that the
  Run page's Figures tab draws. A heatmap may carry named slices (attention: one per layer and
  head) that the tab switches between.
- SAEs: loaded by SAELens (`SAE.from_pretrained` or `load_from_disk`) in the `sae` extra, which
  is heavy (SAELens pulls in TransformerLens and wandb) and imported only when an SAE is used.
  loupe reads the residual at the SAE's hook with nnsight, so the model is never swapped for a
  TransformerLens one; a feature's decoder row saves as a direction like any other.
- Directions: one safetensors file each under `<LOUPE_HOME>/vectors`, provenance in the header. The
  server reads the header without torch, so `loupe serve` never needs the interp extra.
- Every run writes `RunMeta`: commit and dirty flag, package versions, seed; later also model
  revision, dataset fingerprint and chat-template hash.

## UI

The UI is the product. `apps/web` is a static Next.js export served by `loupe serve` next to the
API, so there is no Node server in production. The server owns no database and no auth. Its
one computing route is the Playground, which runs the model given to `loupe serve --model`.

Pages: Home, Experiments, Run (Overview, Figures, Samples, Transcripts, Artifacts, Config), Compare,
Vectors, Playground. Principles: one question per screen, every number links to the samples behind
it, compare is first-class, empty states show the command that fills them, keyboard-first (⌘K and
`G` jumps), view state in the URL. Neuronpedia and Docent are linked from it, not replacements for it: an SAE feature with a Neuronpedia id links to its dashboard from the Figures table and from its saved vector.

Design rules live in `apps/web/AGENTS.md`.

## Product repositories

zipy, SparkyAI and piramid keep their own regression evals in their own CI; those test product
behaviour and change with product code. What moves here: post-training and dataset curation (one
copy instead of two), research experiments, and black-box benchmarking of the products through
their OpenAI-compatible endpoints. The contract is a data format (Inspect logs or OpenAI-style
message JSONL), never an import in either direction.

## Correctness traps the code must test

- Left padding: "last token" positions are per row after padding.
- bf16 steering: add in fp32, cast back; log vector norm relative to the residual norm.
- Chat templates: log the rendered string; pin `enable_thinking` for Qwen3.
- Multi-turn protocols: support generated and forced earlier turns.
- Answer parsing: report the parse-failure rate as a metric.
