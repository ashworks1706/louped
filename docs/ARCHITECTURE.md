# Architecture

## What loupe is

A testbed where an intervention on a language model is something you evaluate, train against and
look inside, with a UI as its main surface. loupe is one app: every capability is launched,
configured and read from its UI. It is built on existing free tools, used as libraries or run in
environments of their own, and never re-implements what one of them does well; what it writes
itself is what joins them: one model, one intervention spec, one data format.

What only loupe does, because no single tool joins these:

- The `loupe/` Inspect provider: any open-weight model under Steer, Ablate or Inject, with a bank
  of adapters live in any subset or by generation phase, causal or masked diffusion, tool agents
  included, so every condition is one eval run.
- Intervened against base, statistically: paired bootstrap differences and flips, sweeps of
  score against KL coherence cost over layer and strength, and grids of conditions by tasks by
  seeds with a moved/held verdict.
- One check as both the Inspect scorer and the GRPO reward, and interp across the checkpoints of a
  training run (a direction's projection, model diffing).
- The Playground: base and intervened replies side by side, with the lens, attention and
  projections of the same prompt.
- The interp views these need (lens, attention, projection, patching, probes, top examples,
  SAE feature dashboards), drawn from JSON the analyses log.
- Launching: every experiment, training config, sweep and command as a form, run as a queued job.

How each integrated tool runs inside loupe:

| Need | Tool | How it runs in loupe |
|---|---|---|
| SAE features and their dashboards | SAELens | Library: `loupe features` computes each feature's density, histogram, top examples and logit effects on any dataset, shown on the Feature page; Neuronpedia's page is a link when the SAE has one |
| Attribution graphs over transcoders | circuit-tracer | Its own environment through uv (it pins transformers): `loupe circuit`, launched from the UI; its viewer is served on the Circuits page |
| Reading transcripts and tool calls in depth | Inspect View | Served at /inspect, a tab on every eval run |
| Representation fine-tuning (LoReFT) | pyreft | Its own environment through uv (it pins transformers): `loupe train reft`, its loss logged live to a training run |
| Hyperparameter search | TRL recipes | `loupe train --sweep`: every combination a run, one summary run comparing them |
| Fast steered serving at scale | EasySteer (a vLLM fork) | Not integrated: loupe serves on one machine and batches through its own provider |

## The tools it composes

| Need | Tool |
|---|---|
| Hooks, caching, patching, steering on real HF models | nnsight |
| SAEs and their feature dashboards | SAELens |
| Attribution graphs | circuit-tracer (own environment) |
| Representation fine-tuning | pyreft (own environment) |
| Linear probes | scikit-learn |
| Evals, multi-turn, agents, coding sandboxes, benchmarks | Inspect AI + inspect_evals |
| SFT, DPO, GRPO, LoRA, hyperparameter sweeps | TRL, PEFT, unsloth |
| Multi-turn RL environments | TRL environment_factory |
| Verifiable tasks and answer checks | reasoning-gym, math-verify |
| Adapter banks, merging, prompt tuning | PEFT |
| Lexical and dense retrieval, reranking, NLI | bm25s, sentence-transformers |
| Tracking | MLflow (self-hosted) and Inspect logs |
| UI | Next.js static export, shadcn/ui, Tailwind, Geist, cmdk, TanStack Query, nuqs, Recharts |
| API | FastAPI |

Rejected: verifiers (pulls in hosted-API clients; TRL's environments cover it), vLLM and cluster
launchers (loupe stays single-machine), TransformerLens (reimplements
architectures, lags new models), Hydra (each tool keeps its
native config; our scripts use tyro), W&B (server not self-hostable for free), a custom plugin
registry (Inspect's registries and Python entry points already exist).

## The one idea: a Policy runs everywhere

```
Policy = model + [interventions] + generation params
```

The same Policy is valid in an Inspect eval (through a loupe model provider, tool agents
included), a TRL training run, the UI Playground, and an activation analysis. "Base", "base + steering", "base +
ablation" and "LoRA checkpoint" are therefore compared by one eval, one scorer and one UI view.
A task's scorer is a plain function wrapped once as an Inspect scorer and once as a reward, so an
eval becomes an RL environment without a rewrite.

## Research domains

loupe is organised by research domain. A question is an experiment in `experiments/`, named for
the question, on a domain's capabilities. Nothing in `src/loupe` knows about any one system: a
system you are studying comes in through what every system has, a model id, an OpenAI-compatible
endpoint, logged model calls in a common format, and its specifics stay in an experiment's options.

| Domain | Capabilities | Experiments |
|---|---|---|
| 0 Mechanisms | directions, patching (residual and per head), lens, probes, SAEs, circuits; head ablation; the pushback task | refusal-direction, sycophancy-pushback, interp-toolkit |
| 1 Evaluation science | `grid`: seeds, paired intervals, moved/held; any model or OpenAI-compatible endpoint as a condition; contamination checks; latency, tokens per second, memory; attention kernels as conditions (`attn`); tool-use scorers | answer-or-decline, inspect-evals-baseline, attention-kernels, coding-agent, agent-sandbox, intercode-ctf |
| 2 Conditioning | prompt text, steering vectors, soft prompts at matched budget | prompt-conditioning |
| 3 Adapters | a bank of LoRA adapters live in any subset, merging (linear, TIES, DARE), overlap | diffusion-adapters |
| 4 Decoding and model families | per-step hooks; phase-routed adapters; masked diffusion (LLaDA, Dream) and its denoising trajectory | diffusion-adapters |
| 5 Retrieval and grounding | BM25, dense, fusion, reranking; recall@k, EM, F1, NLI faithfulness | retrieval-injection |
| 6 Retrieval inside the model | Inject at a layer; retrieval during decoding; spliced KV divergence; attention mass on a passage | retrieval-injection, attention-heads |
| 7 Small models and data | logged calls or a teacher to a reviewed set, hashed splits, SFT, DPO, GRPO, a small classifier | sft-from-traces, refusal-finetuning, gsm8k-grpo, tool-rl |

## Packages and layers

One distribution (`loupelab`), import name `loupe`, one extra per capability so an install carries
only what it uses. A package imports only packages below it; `import-linter` enforces it.

```
experiments                      leaf, nothing imports it
cli
server                           FastAPI over the stores; Playground generation; launch jobs
train | sweep | grid             sft (LoRA, soft prompt, masked diffusion), dpo, grpo, classify,
                                 logged as MLflow training runs; steering sweeps; condition grids
stores | tracking | analysis     views over Inspect logs and MLflow; start an MLflow run;
  | inspect_ext                  lens, patching, probes, attention, SAE features, KV splices as UI
                                 views; loupe/ provider, scorers, pushback and RAG tasks
interventions                    Steer, Ablate and Inject specs on nnsight, batched generation
vectors                          directions as safetensors
models | data | retrieval        load a model into nnsight, adapter banks, masked diffusion;
                                 training sets from traces or a teacher; search and its metrics
core                             run metadata, paths
```

Today everything from `core` to `cli` exists. The scorer-to-reward bridge needs no layer of its
own: a check is a plain function, `inspect_ext.as_scorer` wraps it for Inspect and
`train.rewards.as_reward` for TRL. Each phase adds its layers here and in the contract in
`pyproject.toml`.

## Data

- Evals: Inspect `.eval` logs are the source of truth for transcripts and per-sample scores.
- Everything else: an MLflow run with params, metrics and artifacts. Figures are data, not images:
  JSON under `views/` in one of four shapes (heatmap, line, table, tokens; `loupe.analysis.views`)
  that the Run page's Figures tab draws. A heatmap may carry named slices (attention: one per
  layer and head) and a label per cell (the logit lens's tokens). A tokens view colours texts per
  token by a series the tab picks; with pairs (attention), by the hovered token's row.
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
only computing routes are the Playground's, which run the model given to `loupe serve --model`
(with `--bank` adapters, or `--diffusion` for a masked diffusion model), or one loaded from the
UI: generate, which streams plain text, and inspect, which returns a prompt's views in the same
shapes a run logs.

The Launch page starts what the CLI starts: an experiment script, `loupe train` on a config (edited
in the page, run as a copy), `loupe sweep`, or `inspect eval`. Each form is read from the command's
own argument parser, so a new experiment gets one without UI code. A job is that command in a
subprocess, one at a time, its output under `<home>/jobs`; its runs land in the stores like any
other and show on the Runs page while they write (pages poll while a run is live). Launching and
loading a model run code on this machine, so both are on only for a loopback server, never with
`--expose` (the public demo reads only). It also serves two
viewers it does not own: Inspect View at /inspect, whose API mounts under /api behind loupe's
routes, read-only; and circuit-tracer's graph viewer at /circuit over <home>/graphs.

Pages: Home, Experiments, Launch, Run (Overview, Figures, Samples, Log, Artifacts, Config), Feature, Compare,
Vectors, Circuits, Playground. Principles: one question per screen, every number links to the samples behind
it, compare is first-class, empty states show the command that fills them, keyboard-first (⌘K and
`G` jumps), view state in the URL. An SAE feature opens its own Feature page (density,
histogram, top examples, logit effects), with Neuronpedia's page one link away when the SAE has
one; Inspect View is a tab on every eval run.

Design rules live in `apps/web/AGENTS.md`.

Two surfaces sit outside the package. `apps/site` is the landing page and docs (Next.js and
Fumadocs, on Vercel). `deploy/app` is the public demo: the image with scripted demo runs baked in and no
model, so it has nothing to run and nothing to write.

## Your own systems

An application built on a model keeps its regression evals in its own repository; they test its
behaviour and change with its code. What loupe gives it: benchmarking through its OpenAI-compatible
endpoint (`loupe.grid.endpoint`), training sets from its logged model calls (trace JSONL or
OpenTelemetry GenAI spans in Phoenix), post-training, and the research questions behind it. The
contract is a data format (Inspect logs, OpenAI-style message JSONL, an OpenAI-compatible API),
never an import in either direction.

## Correctness traps the code must test

- Left padding: "last token" positions are per row after padding.
- bf16 steering: add in fp32, cast back; log vector norm relative to the residual norm.
- Chat templates: log the rendered string; pin `enable_thinking` for Qwen3.
- Multi-turn protocols: support generated and forced earlier turns.
- Answer parsing: report the parse-failure rate as a metric.
