# Roadmap

What is built, how far each part has been checked, and what comes next. The design is in
ARCHITECTURE.md.

A result counts once it has run on a real model. "Tiny" means checked end to end on a small model
trained to show the behaviour, which proves the pipeline and nothing about the claim. Real runs
below were on one 6 GB laptop GPU (RTX 4050).

## Change a model

- [x] Intervention specs, one format everywhere: `steer`, `ablate`, `inject`, `heads` (zero or
      mean ablation of attention heads). Real: ablating the refusal direction of
      Qwen2.5-0.5B-Instruct takes harmful refusal from 73% to 0%, adding it takes harmless refusal
      from 9% to 98%, as Arditi et al. report.
- [x] Training recipes on TRL and PEFT from one YAML: `sft` (LoRA, 4-bit QLoRA, soft prompts,
      masked diffusion), `dpo`, `grpo` (reward functions or a tool environment), `classify`.
      Real: SFT in 4-bit, DPO removing refusal (73% to 0% by the first checkpoint), GRPO on GSM8K.
- [x] `loupe train reft`: LoReFT through pyreft in its own environment. Real: a smoke run.
- [x] `loupe train --sweep key=a,b`: every combination a run, one summary run comparing them. Real:
      a two-value learning-rate sweep.
- [x] Adapter banks: named LoRAs live in any subset, merged (linear, TIES, DARE), switched by
      generation phase. Tiny.
- [x] Masked diffusion models (LLaDA, Dream, nanoDiff checkpoints, any masked LM): sampled with a
      per-step hook, trained on their own objective, served. Tiny; real ones need more than 6 GB.
- [x] Retrieval into the prompt (BM25, dense, fused, reranked) or injected at a layer. Real on
      Qwen2.5-0.5B: passages in the prompt raise F1 from 0.01 to 0.46; injected at layer 12, 0.00.
- [x] Training sets from logged model calls (trace JSONL, OpenTelemetry spans in Phoenix) or a
      teacher: redaction, verification, a review ledger, curation, hashed splits.
- [x] Tool use trained offline: a replay environment serves recorded tool outputs to GRPO, the
      recordings taken from logged calls (`loupe.train.replay`).

## Prove what changed

- [x] The `loupe/` Inspect provider: any open-weight model under any spec, with adapters, tools and
      batching (twice as fast on a GPU, identical scores; a batch out of memory is halved).
- [x] `loupe grid`: conditions by tasks by seeds against a baseline, paired bootstrap intervals, a
      moved/held verdict. Any model or OpenAI-compatible endpoint is a condition.
- [x] Compare: two runs sample by sample, flips and paired intervals.
- [x] `loupe sweep`: a task under Steer at every layer and strength, with the coherence cost.
- [x] Inference cost as scores: latency, tokens per second, peak memory, time to first token (the
      provider's own, or streamed from an endpoint).
- [x] inspect_evals benchmarks through the provider. Real: GSM8K 38% ± 7% on 50 samples of
      Qwen2.5-0.5B-Instruct against the reported 49.6%.
- [x] `experiments/benchmarks`: SQuAD, DROP, BFCL, TruthfulQA and GSM8K on any model or endpoint,
      one grid per benchmark. Real: a 3-sample check of SQuAD, TruthfulQA and BFCL.
- [x] Agents in Docker under interventions, with tool-use scorers. Real on Qwen2.5-1.5B: a sandbox
      task, hidden-test coding and five InterCode CTF tasks.
- [x] Opaque agents: the `agent/` provider calls any agent behind an OpenAI-compatible endpoint and
      reads the tool calls and sources it reports in a `trace` field, so tool scorers work on a
      system that runs its own tools.
- [x] Regression cases: a JSONL of questions with expectations (tool, arguments, cited source,
      required and forbidden phrases, declining) as an Inspect task, scored the same on a local
      model or an agent (`experiments/regression-cases`).
- [x] tau2-retail (τ-bench) in `experiments/benchmarks`, the simulated customer played by any model
      through Inspect's user role, which a grid condition now sets (`roles`).

## See why

- [x] Logit lens, attention, residual and per-head patching, attribution patching, probes,
      projections and top examples. Real: attribution patching tracks exact patching (r = 0.80),
      probes reach 100% by layer 6 of Qwen2.5-0.5B.
- [x] SAE features (SAELens) with native dashboards (`loupe features`): density, histogram, top
      examples around each peak, the tokens a feature promotes and suppresses. Real on GPT-2's
      residual SAE; Neuronpedia's page embedded when the SAE has one.
- [x] Attribution graphs (`loupe circuit`, circuit-tracer in its own environment) on the Circuits
      page, adapting to GPU memory. Tiny; Qwen3-0.6B's transcoders do not fit 6 GB.
- [x] Across training: any measure on every checkpoint, model diffing per layer.

## The app

- [x] Runs, Run (figures, samples, Inspect View), Compare, Experiments, Vectors, Circuits, Feature.
- [x] Launch: every experiment, training config, command and eval as a form, run as a queued job.
- [x] Live runs: status and progress refresh while a run writes.
- [x] Playground: base and changed replies side by side, the lens of the same prompt, a model
      loaded from the UI.

## Acceptance

- [x] Reproduce the refusal direction on a Qwen2.5 instruct model, read in the UI.
- [ ] An inspect_evals score within noise of the reported number on the full split.
- [ ] GRPO on GSM8K on a small Qwen shows the known gain (500 steps).
- [ ] One mechanism result per domain on a real model, read entirely in the UI.
- [ ] A fresh user runs an example from a clean clone.

## Next

- Diff first: Compare as the home page, a base and a changed version picked in one step, model
  versions and 4-bit quantization as conditions.
- More benchmarks: IFEval (needs its optional package), a memory benchmark across conversations
  (LongMemEval or LoCoMo), citation accuracy (ALCE), a long-context one that fits a laptop disk,
  and a HotpotQA grounding task with its paragraphs retrieved or injected.
- Retrieval inside the model: a sweep over layer and strength before any fused design is built.
- Sycophancy on a 1.5B to 3B model, where a caving direction is worth publishing.
- RunMeta with the model's revision, a dataset fingerprint and the chat template's hash.
- Deploy the docs site and the read-only demo.
