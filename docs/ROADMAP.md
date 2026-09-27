# Roadmap

loupe builds the joins between interventions, evals, training and interp, and links to existing
tools for the rest (ARCHITECTURE.md). Out of scope, because other free tools do it: a training
dashboard, cluster and vLLM scale-out (Transformer Lab, LLaMA-Factory, Oumi), SAE and graph
browsing (Neuronpedia, circuit-tracer), ReFT (pyreft).

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
- [x] Model diffing: per layer, residual cosine, norm change and the cosine of a contrast
      direction between two models of one architecture
- [x] Attribution graphs: circuit-tracer runs in its own environment (`just circuit`); its viewer
      is served by loupe on the Circuits page
- [x] SAE features link to Neuronpedia's dashboard, embedded beside the table; `just neuronpedia`
      runs it locally in Docker and the links follow (`LOUPE_NEURONPEDIA` for another host)
- [ ] Acceptance: reproduce the refusal direction (Arditi et al. 2024) on a Qwen2.5 instruct model,
      read entirely in the UI

## v0.4 Evals bridge and Playground

- [x] `loupe/<model>` Inspect model provider taking intervention specs as model args; shared
      `refusal` scorer
- [x] Playground (`loupe serve --model`): base and intervened replies side by side, steer or
      ablate, layer and strength, the spec as a copyable `-M interventions=...`
- [x] Verified offline: `refusal-direction/eval.py --tiny` runs base and ablated through the
      provider, Compare shows harmful refusal 1 to 0 on all 12 harmful samples
- [x] Replies stream token by token, with a stop that ends generation on the server
- [x] Playground: live adapters from a bank (`--bank`), masked diffusion models (`--diffusion`)
      with the denoising trajectory, and head ablation
- [x] Paired comparison in Compare: beside the per-sample flips, each score's paired difference
      with a seeded bootstrap interval and the count of samples that went up and down
- [x] `loupe sweep`: a task under Steer at every layer and strength, as heatmaps of score and of
      coherence cost (KL on neutral prompts), a line of score against strength, and a table
      linking every cell's eval run
- [x] `experiments/inspect-evals-baseline`: inspect_evals GSM8K base and ablated, against Qwen's
      reported number (not yet run)
- [ ] Acceptance: an inspect_evals score within noise of the reported number; steered and base in Compare

## v0.5 Training

- [x] `loupe data`: export (zipy traces, Phoenix spans), redact, verify, review ledger, curate
- [x] `loupe train sft`: LoRA SFT on TRL and PEFT (any device) or Unsloth QLoRA with GGUF export
      (CUDA); loss on the reply only; MLflow training runs; merged model loadable as `loupe/<name>`
- [x] Migrated post-training and curation from zipy and SparkyAI and removed them there; their
      product regression evals stay in their repos
- [x] `loupe train dpo` and `loupe train grpo` on TRL, sharing sft's config, backends, runs,
      checkpoints and export
- [x] One plain check is an Inspect scorer (`as_scorer`) and a GRPO reward (`file.py:function`)
- [x] Training dynamics: any measure re-run on the base and every kept checkpoint, as a line
      against step
- [x] `experiments/refusal-finetuning`, verified offline (`--tiny`): DPO on the model's own ablated
      replies; refusal and the direction's projection both collapse by step 5
- [x] `experiments/gsm8k-grpo`: data, recipe and eval for the acceptance below (not yet run)
- [ ] Acceptance: GRPO on GSM8K on a small Qwen shows the known gain

## v0.6 Agentic and coding

- [x] Tool-call transcript view: calls, arguments, results and errors as their own blocks
- [x] The loupe/ provider takes tools: schemas through the chat template, calls parsed by
      Inspect's Hugging Face handler, tokens counted by the model's tokenizer; so agents run under
      interventions
- [x] `experiments/agent-sandbox`: bash in a Docker sandbox, verified with the tiny model and
      scripted calls
- [x] Multi-turn agent RL: `environment: file.py:Class` in a GRPO config is a TRL environment
      (per-rollout state, its methods as tools, an optional episode reward); every logged step's
      rollouts kept and the first and last shown as a Rollouts figure
- [x] Verifiable tasks from reasoning-gym (procedural, offline) and maths answers checked by
      math-verify, as plain checks (`loupe.train.tasks`), so reward and scorer stay one function
- [x] `experiments/tool-rl`: calculator and submit tools over reasoning-gym arithmetic, reward
      from the environment (not yet run)
- [x] Inspect View served by loupe at /inspect, read-only over its logs, as an Inspect tab on
      every eval run, opened at the selected sample
- [x] Tool-use scorers (calls, errors, required tool, answer grounded in a tool result) usable as
      grid metrics; `experiments/coding-agent`: hidden-test coding in Docker, HumanEval format
- [x] `experiments/intercode-ctf`: inspect_evals InterCode CTF through loupe/, verified with scripted
      calls in Docker (not yet run on a model)
- [ ] Acceptance: an inspect_evals agentic task end to end in Docker

## v0.7 Research domains

The research questions of the ARC thesis, zipy (which now includes Bijou), SparkyAI and piramid, as reusable domains
(ARCHITECTURE.md). Product regression evals and performance numbers stay in each product's repo.

- [x] Grid: conditions by tasks by seeds, each against a baseline with a paired bootstrap interval
      and a moved/held verdict (`loupe grid`); a condition may be another Inspect model
- [x] Mechanisms: `experiments/sycophancy-pushback` (caving direction, patching, mitigation
      grid on Sharma et al.'s are_you_sure); run offline with `--tiny` only
- [x] Conditioning: soft prompts (PEFT prompt tuning) trained by sft and merged as new tokens
- [x] Adapters: a bank of named LoRAs live in any subset through the provider, PEFT merges,
      per-site overlap; sft keeps an adapter by name for the bank
- [x] Decoding: a per-step hook in both samplers; adapters switched by phase; masked diffusion
      models (LLaDA, Dream, any masked LM) sampled, trained on their own objective and served
- [x] Retrieval: BM25 and dense search fused by rank, reranking, a RAG task scored on recall,
      EM, F1 and NLI faithfulness
- [x] Retrieval inside the model: Inject at a layer through the provider, retrieval during
      decoding, spliced KV divergence with and without the rotary phase error
- [x] Small models and data: teacher collection, hashed splits, n-gram contamination, a
      classifier recipe
- [x] Black box: one experiment per product through its OpenAI-compatible endpoint
      (`experiments/{sparky,zipy,piramid}-blackbox`), verified against mocks and a local stub
- [x] Attention: a Heads spec (zero or mean ablation), per-head patching, attention mass on a span;
      latency, tokens per second and peak memory as grid metrics (`experiments/attention-heads`)
- [x] Diffusion: the denoising trajectory as a view; `experiments/diffusion-adapters` (skills,
      merged, phase-routed) run offline with `--tiny`
- [ ] Acceptance: one result per project read entirely in the UI, on a real model

## v1.0 Open source

- [x] Docs site (apps/site) and a read-only demo image (deploy/app)
- [x] Three worked examples and a model support page in the docs; `just examples` runs the
      offline examples from a clean clone in CI
- [ ] The site and demo deployed
- [ ] Acceptance: a fresh user runs an example from a clean clone
