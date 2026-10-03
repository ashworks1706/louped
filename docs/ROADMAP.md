# Roadmap

loupe grows when an experiment needs it. Each item below is a research outcome or the check that
makes one trustworthy; the experiment it lives in is named.

## Acceptance

Behavior and alignment:

- [ ] Experiment 1A: the rational-updating harness reproduces the published unmitigated
      Llama-3.1-8B-Instruct baseline on TruthfulQA, rates and denominators within the README's
      margin, with ten examples read by hand (`rational-updating-baseline`).
- [ ] One mechanism result on a real model, read entirely in the UI.

Efficiency and systems:

- [ ] None yet; questions come later.

Instrument checks:

- [ ] An inspect_evals score within noise of the reported number on the full split.
- [ ] GRPO on GSM8K on a small Qwen shows the known gain in 500 steps.

## Next

- A human-calibration study in `honesty`: an agent adapting to a simulated person over repeated
  turns, with no personal state, ordinary preference memory, and preferences kept apart from
  factual claims, scored on useful adaptation and on correctness under pressure.
- More checks: IFEval (needs its optional package), a memory benchmark across conversations
  (LongMemEval or LoCoMo), citation accuracy (ALCE), and a HotpotQA grounding task with its
  paragraphs retrieved or injected.
- RunMeta with the model's revision, a dataset fingerprint and the chat template's hash.
- Deploy the docs site.
