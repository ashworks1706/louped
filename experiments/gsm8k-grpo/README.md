# gsm8k-grpo

## Question

Does GRPO with a correctness reward raise a small instruct model's GSM8K test accuracy, as
reported for Qwen2.5 models (a gain of several points within a few hundred steps)?

## What would answer it

Greedy test accuracy, base against GRPO, on the same samples: the paired difference and its
bootstrap interval in Compare. A gain whose interval excludes zero reproduces; one inside noise
does not. The reward and the scorer are the same function (`checks.py:correct`).

## Run

Needs a GPU for reasonable time; everything is local.

```sh
uv run --all-extras python experiments/gsm8k-grpo/data.py
loupe train grpo experiments/gsm8k-grpo/grpo.yaml --dry-run
loupe train grpo experiments/gsm8k-grpo/grpo.yaml
uv run --all-extras python experiments/gsm8k-grpo/eval.py
```

The training run shows loss and `rewards/correct` by step; the two evals compare under Compare.

## Result

Not yet run: this environment cannot reach huggingface.co. The recipe itself is covered by the
CPU test in `tests/test_train.py` (GRPO on the tiny model with a check loaded from a file).
