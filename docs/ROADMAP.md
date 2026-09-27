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
- [ ] Acceptance: an inspect_evals score within noise of the reported number; steered and base in Compare

## v0.5 Training

- [x] `loupe data`: export (zipy traces, Phoenix spans), redact, verify, review ledger, curate
- [x] `loupe train sft`: LoRA SFT on TRL and PEFT (any device) or Unsloth QLoRA with GGUF export
      (CUDA); loss on the reply only; MLflow training runs; merged model loadable as `loupe/<name>`
- [x] Migrated post-training and curation from zipy and SparkyAI and removed them there; their
      product regression evals stay in their repos
- [ ] DPO and GRPO recipes; pyreft; scorer-to-reward bridge
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
