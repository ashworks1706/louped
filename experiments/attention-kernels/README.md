# attention-kernels

## Question

What does each attention kernel cost in task accuracy, latency, output tokens per second and peak
memory, and how far do its predictions drift from eager attention? Exact kernels (sdpa, flex,
flash) should match eager on accuracy and differ only in cost; approximate ones (a sliding window,
top-k sparse attention) trade accuracy for it.

## What would answer it

- Agreement: on the answer token of each test prompt (the reply prefilled up to it), mean
  KL(eager || kernel) near 0 and top-1 agreement 1.0 for the exact kernels.
- A grid over recall questions (two facts in context, the first asked for, so a short window
  cannot see it): `correct_first/accuracy` against eager with a paired interval, and latency,
  tokens per second and peak CUDA memory beside it.
- The claim fails if an exact kernel moves accuracy beyond sample variance, or if an approximate
  kernel keeps accuracy while its agreement with eager is low.

## Kernels

A condition is `{"attn": ...}`, the same model arg `-M attn=...` takes: `eager`, `sdpa`,
`flash_attention_2` (added when `flash_attn` is installed on CUDA), `flex_attention`, any name
registered with transformers' `AttentionInterface`, or `file.py:function`, which loupe imports and
registers under the function's name with the eager mask. `kernels.py` holds two in plain torch:

- `sliding_window`: causal attention over the last `WINDOW` (8) keys.
- `top_k`: causal attention over each query's `TOP_K` (4) highest-scoring keys.

Edit `kernels.py` or add a function there to try another; attention views and head ablation run on
any of them (views switch to eager for their own trace).

## Run

```sh
uv run --all-extras python experiments/attention-kernels/run.py --tiny   # offline, a 4-layer toy
uv run --all-extras python experiments/attention-kernels/run.py          # Qwen2.5-0.5B-Instruct
uv run --all-extras python experiments/attention-kernels/run.py --profile   # plus chrome traces
```

A number reported from a real model records the Hub commit it ran at: pass `--revision`. With
`--profile`, the analysis run holds `profiles/<kernel>.json`, a torch.profiler chrome trace of one
generation per kernel (open in Perfetto or chrome://tracing).

## Result

Qwen2.5-0.5B-Instruct (2026-09-27): sdpa and flex_attention agree with eager (KL 0.008, top-1
agreement 0.94); the sliding window of 8 does not (KL 3.56, top-1 0.13), and top-4 keys partly
(KL 0.71, top-1 0.44).

`--tiny --profile` (seed 0; a 4-layer, 4-head toy trained on 300 questions; 16 held out; CPU):

| kernel         | accuracy (vs eager)    | KL(eager \|\| kernel) | top-1 agreement | latency s | tokens/s |
| -------------- | ---------------------- | --------------------- | --------------- | --------- | -------- |
| eager          | 1.00                   | 0                     | 1.00            | 0.51      | 10.9     |
| sdpa           | 1.00 (+0.00)           | 0                     | 1.00            | 0.26      | 26.1     |
| flex_attention | 1.00 (+0.00)           | 0                     | 1.00            | 2.55      | 1.6      |
| sliding_window | 0.12 (-0.88, [-1.00, -0.69]) | 7.77            | 0.12            | 0.29      | 23.5     |
| top_k          | 1.00 (+0.00)           | 0.0006                | 1.00            | 0.32      | 20.9     |

The window of 8 cannot reach the asked fact and loses the task; top-4 keeps it, since the toy puts
nearly all of the answer position's attention on a few keys. flex_attention runs uncompiled on CPU,
hence its latency. Peak memory is 0 off CUDA. Latency on a toy on a shared CPU says little about a
real model on a GPU; the toy checks the mechanics, not a claim about kernels.
