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

- [ ] Server: runs from MLflow, eval logs and samples from Inspect logs
- [ ] OpenAPI types generated into the UI
- [ ] Runs, Run, Samples, Transcripts, Compare pages
- [ ] Acceptance: a new user explains a run from the UI alone

## v0.3 Interp core

- [ ] `models`, `interventions`, `vectors`, `analysis` on nnsight; Interp tab; Vectors page
- [ ] Acceptance: reproduce the refusal direction (Arditi et al. 2024) on a Qwen2.5 instruct model,
      read entirely in the UI

## v0.4 Evals bridge and Playground

- [ ] Policy as an Inspect model provider; shared scorers
- [ ] Playground: base and steered streamed side by side
- [ ] Acceptance: an inspect_evals score within noise of the reported number; steered and base in Compare

## v0.5 Training

- [ ] SFT, DPO, GRPO recipes on TRL and PEFT; pyreft; scorer-to-reward bridge
- [ ] Migrate post-training and curation from zipy and SparkyAI, then remove them there
- [ ] Acceptance: GRPO on GSM8K on a small Qwen shows the known gain

## v0.6 Agentic and coding

- [ ] Inspect sandboxes and tool agents, verifiers tool environments, tool-call transcript view
- [ ] Black-box benchmarking of zipy, SparkyAI and piramid through their endpoints
- [ ] Acceptance: an inspect_evals agentic task end to end in Docker

## v0.7 Scale-out

- [ ] submitit and SkyPilot launchers; nnsight vLLM backend
- [ ] Acceptance: a steered sweep on a cluster matches local results

## v1.0 Open source

- [ ] Docs site, three worked examples, model support matrix, hosted read-only demo
- [ ] Acceptance: a fresh user runs an example from a clean clone
