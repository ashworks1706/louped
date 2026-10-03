# Roadmap

loupe grows when an experiment needs it. Each item below is a research outcome or the check that
makes one trustworthy; the experiment it lives in is named.

## Acceptance

Behavior and alignment:

- [ ] One mechanism result on a real model, read entirely in the UI (`mechanisms`; the next question
      comes from the ARC lab).
- [ ] Sycophancy on a 1.5B to 3B model: a caving direction past the early layers, or evidence there
      is none (`sycophancy-pushback`).

Efficiency and systems:

- [ ] Retrieval inside the model: a sweep over injection layer and strength on a real model, before
      any fused design is built, and a stated answer to which layer, if any, carries the passages
      (`retrieval-injection`).

Instrument checks:

- [ ] An inspect_evals score within noise of the reported number on the full split
      (`inspect-evals-baseline`).
- [ ] GRPO on GSM8K on a small Qwen shows the known gain in 500 steps.
- [ ] A fresh user runs an example from a clean clone.

## Next

- A human-calibration study in `honesty`: an agent adapting to a simulated person over repeated
  turns, with no personal state, ordinary preference memory, and preferences kept apart from
  factual claims, scored on useful adaptation and on correctness under pressure.
- Harder questions for `answer-or-decline`: the built-in set does not separate a 0.5B model from a
  7B one.
- More checks: IFEval (needs its optional package), a memory benchmark across conversations
  (LongMemEval or LoCoMo), citation accuracy (ALCE), and a HotpotQA grounding task with its
  paragraphs retrieved or injected.
- RunMeta with the model's revision, a dataset fingerprint and the chat template's hash.
- Deploy the docs site and the read-only demo.
