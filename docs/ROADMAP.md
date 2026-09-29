# Roadmap

## Acceptance

- [ ] An inspect_evals score within noise of the reported number on the full split.
- [ ] GRPO on GSM8K on a small Qwen shows the known gain (500 steps).
- [ ] One mechanism result per domain on a real model, read entirely in the UI.
- [ ] A fresh user runs an example from a clean clone.
- [ ] proper UI redesign and account workflow

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
