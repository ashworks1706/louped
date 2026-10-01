---
domain: mechanisms
status: answered
---

# attention-heads

## Question

Which attention heads carry an answer read from a passage in context, and does ablating them
remove the ability (accuracy drops beyond sample variance) while ablating as many random heads
does not? What does each ablation do to latency and output tokens per second?

## What would answer it

- Per-head patching (clean and corrupt differ only in the asked fact's value), averaged over
  pairs: a few heads restore most of the clean answer, and the same heads put a large share of the
  last position's attention on the asked passage.
- A grid over held-out questions: `correct_first/accuracy` drops for the top heads (zero and mean
  ablated) with a paired interval that excludes zero, and stays for the random-heads control.
  Latency, tokens per second and peak CUDA memory are reported beside it, not averaged into it.
- The claim fails if the random heads cost as much as the top heads, or if the top heads by
  patching are not the heads that attend to the passage.

## Run

```sh
uv run --all-extras python experiments/attention-heads/run.py --tiny   # offline, a 4-layer toy
uv run --all-extras python experiments/attention-heads/run.py          # Qwen2.5-0.5B-Instruct
uv run --all-extras python experiments/attention-heads/run.py --revision <commit>   # pinned
```

A number reported from a real model records the Hub commit it ran at: pass `--revision`.

Two runs appear under Runs: the analysis (head patching heatmap, attention on the passage by layer
and head, the ablated heads) and the grid (accuracy, its paired difference against base, latency,
tokens per second and peak memory (0 off CUDA), each cell linking to its eval samples). The head
spec a condition uses is the same one `-M interventions=...` takes:

```json
{"kind": "heads", "layers": [2], "heads": [0, 3]}
{"kind": "heads", "layers": [2], "heads": [0, 3], "mode": "mean", "over": ["text", "..."]}
```

## Result

Qwen2.5-0.5B-Instruct (2026-09-27): the heads that restore the most of the clean answer when patched
are 21.2, 23.11 and 20.7 (0.144, 0.143 and 0.138).

`--tiny` (seed 0; a 4-layer, 4-head toy trained on 240 questions; 16 held out; mean ablation over 8
training questions). Head patching over 6 pairs puts the answer in head 0.2 (0.72 of
the clean answer restored) and heads 3.1 and 3.0 (0.21, 0.19); every other head is under 0.07.
Those three heads put 0.99, 1.00 and 0.99 of the last position's attention on the asked passage.
Accuracy 1.00 at base drops to 0.06 with them zeroed and 0.12 mean-ablated (paired intervals
[-1.00, -0.81] and [-1.00, -0.69]); three random heads cost 0.31 ([-0.56, -0.13]), which patching
does not predict (each of them restores under 0.02). Latency (0.45 to 0.73 s per sample) and tokens
per second (6.2 to 15.8) moved between conditions by more than an ablation can explain on a machine
shared with other jobs, and ablated replies are shorter; read them on a quiet GPU. Peak memory is 0
on CPU. The toy checks the mechanics, not a claim about real models.
