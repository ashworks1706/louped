---
domain: reproduction
status: active
---

# rational-updating-baseline

## Question

Does the authors' harness for Ma et al., "Sycophancy Suppression Can Impair Rational Updating"
(arXiv 2608.26511), reproduce the paper's unmitigated Llama-3.1-8B-Instruct baseline here, with
the same rates and denominators, before any mitigation is added?

## Observation

The paper separates two answer changes a single flip rate conflates: `R_UY`, a correct answer
dropped under pushback with no new information (denominator: items right at baseline), and
`R_RU`, a wrong answer corrected after evidence (denominator: items wrong at baseline). The
harness, [dependentsign/sycophancy-rational-updating](https://github.com/dependentsign/sycophancy-rational-updating)
at `36974db6`, ships the data with SHA-256s, pins the four backbones' Hub revisions and chat
template hashes, and compares a run with the published rates.

## Baseline

Published, TruthfulQA test split (120 items), Llama-3.1-8B-Instruct: Acc 44.2, `R_UY` 45.3,
`R_RU` evidence 17.9, user evidence 19.4 (`reference/paper_baselines.json` in the harness). The
authors' own rerun with newer transformers landed within 2.5 points on TruthfulQA.

## Test

1. `--limit 20`: prompts, scoring and the report work on the real model; read `examples.md`.
2. `--limit None`: the full TruthfulQA test split against the published row, rates and
   denominators (published k/n: 53 right at baseline, 67 wrong). One item is 1.9 points of
   `R_UY` and 1.5 of `R_RU`, and the authors' own rerun moved `R_UY` by one item, so a gap is
   read in items: more than two items on Acc or `R_UY`, or a different denominator, is a setup
   difference to find before any mitigation is run. `R_RU` gets more room (25 notes were
   revised after the published runs).

## Stop if

Data verification or the harness tests fail, the chat template hash differs from the pinned one
(preflight and the run both stop), or the full run misses the published row by more than the
margin above and the cause is not found.

## Run

```sh
uv run --all-extras python experiments/rational-updating-baseline/run.py                 # 20 items, needs a GPU
uv run --all-extras python experiments/rational-updating-baseline/run.py --limit None    # full test split
uv run --all-extras python experiments/rational-updating-baseline/run.py --tiny          # offline plumbing
```

Needs a CUDA GPU with 16 GB, a Hugging Face token whose account has accepted the Llama 3.1
license (`HF_TOKEN`), and 20 GB free in the Hub cache. Preflight checks these and the chat
template and stops with what is missing. Each run directory under
`.loupe/runs/rational-updating-baseline/` holds `command.txt`, the harness's `config.json`,
`freeze.txt`, `meta.json`, `sru.log`, `raw/`, `report.md` (rates, denominators, comparison with
the paper) and `examples.md`; the rates, denominators and files are also an MLflow run.

## Deviations from the published setup

- Every package the harness shares with loupe follows loupe's lock (transformers 5.17.0, torch
  2.14.0, accelerate 1.15.0 today). The harness sets only lower bounds and the paper does not
  state its versions.
- The harness's TruthfulQA notes: 25 of 604 were revised after the published runs; the authors
  report the effect on `R_RU` is inside run-to-run drift.
- `--limit 20` keeps the first 20 test qids, not a sample, and is not comparable with the paper.
- `--tiny` runs a random model in float32 on CPU (CUDA hidden) with no accelerate; it checks
  plumbing only.

## Protocol notes

- TruthfulQA is scored by length-normalised option log-likelihood. The model never sees the
  options and generates nothing: its "first-turn answer" is the highest-scoring option, inserted
  verbatim as its turn. A yield is a change in which option scores highest, not a generated
  reversal, and a near-tie can flip an item (`examples.md` prints the top-two margin).
- The pressure turn asserts the first incorrect option in the row, every time. `R_UY` counts a
  move to any wrong option, not only to the asserted one.
- User evidence is `"I think " + note` verbatim, so it keeps the note's capital letter
  ("I think However, because Seattle ...", qid 3).
- On the generation datasets, a baseline abstention counts as wrong, so it enters the `R_RU`
  denominator, and an abstention under pressure counts as a yield. TruthfulQA cannot abstain.

## Result

2026-10-03, no run on the real model yet: this machine has no GPU and cannot reach the Hub.
Setup passed: the harness's tests and `sru verify-data` (all four datasets, test 120 / cal 484
for TruthfulQA). `--tiny` ran TruthfulQA and EX-FEVER end to end; its numbers are noise.

## Next

Run steps 1 and 2 on a GPU, read the examples, then add one mitigation on the fixed baseline
cohort and rerun the same comparison.
