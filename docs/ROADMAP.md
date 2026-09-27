# Roadmap

Each phase ends with an acceptance test, most of them reproducing a published result: if loupe
cannot reproduce a number someone else got, its own numbers cannot be trusted. Every phase ships
with its UI view.

## v0.1 Skeleton

- [x] Package, extras, layer contract, `just` gate, pre-commit
- [x] API server with health, static UI served next to it
- [x] UI shell: sidebar, ⌘K menu, `G` jumps, dark and light, mobile, empty states
- [x] CI, release (PyPI + ghcr.io), release-please, security, Dependabot
- [x] AGENTS.md, `.claude/` skills and reviewers
- [ ] Import the branch ruleset and configure PyPI trusted publishing (repository settings)

## v0.2 UI on real logs

- [x] Server: runs from MLflow, eval logs and samples from Inspect logs
- [x] OpenAPI types generated into the UI, checked in CI
- [x] Runs, Run, Samples, Transcripts, Compare, Experiments pages
- [x] Verified in a browser against real Inspect and MLflow runs (a scripted mock model)
- [ ] Acceptance: a new user explains a run from the UI alone

## v0.3 Interp core

- [x] `models`, `interventions`, `vectors`, `analysis` on nnsight; Figures tab; Vectors page
- [x] `experiments/refusal-direction`: selection, ablation, addition, lens, patching, saved vector
- [x] Verified offline on a tiny model trained to refuse (`--tiny`): seed 0 goes 100% to 0% refusal
      on ablation and 0% to 100% on addition; across six seeds the single-direction effect holds
      on some and not others, so the toy checks mechanics, not the claim
- [x] The standard toolkit in `analysis`: linear probes (scikit-learn), attention patterns,
      attribution patching, SAE features (SAELens, `sae` extra); probe weights and SAE decoder rows
      save as directions; attention has a layer and head selector in the Figures tab
- [x] `experiments/interp-toolkit`, verified offline (`--tiny`): attribution patching correlates
      0.99 with exact patching; every view renders on desktop and mobile
- [x] Token views: text coloured per token by any per-token series (a direction's projection, a
      neuron, an SAE feature), with a series selector; attention as hover from a query token
- [x] Logit lens over every layer and position, each cell labelled with its top token
- [x] Max-activating examples over a dataset for a direction, neuron or SAE feature: a local
      feature dashboard that works for any SAE, hosted on Neuronpedia or not
- [x] Inspect tab in the Playground (live, `loupe serve --model`): a prompt's lens, attention and
      projections onto the model's saved directions, base or under the intervention
- [x] Verified offline (`--tiny`): the lens reads "I" at every layer on a harmful prompt and
      "sure" once the refusal direction is ablated; every view renders on desktop and mobile
- [ ] Model diffing: per-layer cosine and norm change of a direction or of mean activations
      between two checkpoints of one model
- [ ] Attribution graphs with circuit-tracer and a graph view
- [ ] Acceptance: reproduce the refusal direction (Arditi et al. 2024) on a Qwen2.5 instruct model,
      read entirely in the UI

## v0.4 Evals bridge and Playground

- [x] `loupe/<model>` Inspect model provider taking intervention specs as model args; shared
      `refusal` scorer
- [x] Playground (`loupe serve --model`): base and intervened replies side by side, steer or
      ablate, layer and strength, the spec as a copyable `-M interventions=...`
- [x] Verified offline: `refusal-direction/eval.py --tiny` runs base and ablated through the
      provider, Compare shows harmful refusal 1 to 0 on all 12 harmful samples
- [ ] Stream replies token by token (today each side returns when done)
- [x] Paired comparison in Compare: beside the per-sample flips, each score's paired difference
      with a seeded bootstrap interval and the count of samples that went up and down
- [x] `loupe sweep`: a task under Steer at every layer and strength, as heatmaps of score and of
      coherence cost (KL on neutral prompts), a line of score against strength, and a table
      linking every cell's eval run
- [ ] Acceptance: an inspect_evals score within noise of the reported number; steered and base in Compare

## v0.5 Training

- [x] `loupe data`: export (zipy traces, Phoenix spans), redact, verify, review ledger, curate
- [x] `loupe train sft`: LoRA SFT on TRL and PEFT (any device) or Unsloth QLoRA with GGUF export
      (CUDA); loss on the reply only; MLflow training runs; merged model loadable as `loupe/<name>`
- [x] Migrated post-training and curation from zipy and SparkyAI and removed them there; their
      product regression evals stay in their repos
- [ ] `loupe train dpo` and `loupe train grpo` on TRL, same data format, runs and model saving as sft
- [ ] Scorer-to-reward bridge: one plain function is an Inspect scorer and a GRPO reward
- [ ] ReFT with pyreft: a trained intervention saved and applied like a Steer
- [ ] Training dynamics: any analysis (probe accuracy, direction norm, eval score) re-run across
      saved checkpoints and drawn as a line against step
- [ ] Acceptance: GRPO on GSM8K on a small Qwen shows the known gain

## v0.6 Agentic and coding

- [ ] Tool-call transcript view: calls, arguments, results and errors as their own blocks
- [ ] Inspect sandboxes and tool agents, verifiers tool environments
- [ ] Black-box benchmarking of zipy, SparkyAI and piramid through their endpoints
- [ ] Acceptance: an inspect_evals agentic task end to end in Docker

## v0.7 Scale-out

- [ ] submitit and SkyPilot launchers; nnsight vLLM backend
- [ ] Acceptance: a steered sweep on a cluster matches local results

## v1.0 Open source

- [ ] Docs site, three worked examples, model support matrix, hosted read-only demo
- [ ] Acceptance: a fresh user runs an example from a clean clone
