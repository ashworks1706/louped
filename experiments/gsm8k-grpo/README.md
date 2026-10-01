---
domain: reproduction
status: parked
---

# gsm8k-grpo

## Question

Does GRPO with a correctness reward raise a small instruct model's GSM8K test accuracy by the
gain others report for Qwen2.5-0.5B-Instruct?

## What would answer it

Greedy test accuracy, base against GRPO, on the same 1319 test samples: the paired difference and
its bootstrap interval in Compare. A gain whose interval excludes zero and sits near the reference
reproduces; one inside noise does not. The reward and the scorer are the same function,
math-verify's symbolic answer check (`loupe.train.tasks:math_equal`).

Expected, from verl's algorithm baselines (`docs/algo/baseline.md` in volcengine/verl, GSM8K test
score): Qwen2.5-0.5B-Instruct 49.6 as released, 54.3 after GRPO with LoRA (+4.7 points; PPO
reaches 56.7). The same table has Qwen2.5-1.5B-Instruct 73.2 to 77.9. Their prompt and answer
format differ from this recipe's, so compare the gain, not the absolute accuracy.

## Run

Needs a CUDA GPU for reasonable time; everything else is local. `data.py` downloads openai/gsm8k
from the Hub once.

```sh
uv run --all-extras python experiments/gsm8k-grpo/data.py
uv run --all-extras loupe train grpo experiments/gsm8k-grpo/grpo.yaml --dry-run
uv run --all-extras loupe train grpo experiments/gsm8k-grpo/grpo.yaml
uv run --all-extras python experiments/gsm8k-grpo/eval.py
```

Training runs 500 steps of 2 prompts by 8 completions and saves the merged model as
`qwen2.5-0.5b-gsm8k-grpo` under LOUPE_HOME; `eval.py` then scores `loupe/Qwen/Qwen2.5-0.5B-Instruct`
and `loupe/qwen2.5-0.5b-gsm8k-grpo` on the whole test split (`--limit 50` for a smoke run). The
training run shows loss and `rewards/math_equal` by step and a Rollouts figure; select the two eval
runs under Runs and Compare them for the paired difference.

The reference trained with 64 prompts per step and LoRA rank 32. If the gain lands inside noise,
raise `train.gradient_accumulation` (prompts per step) before anything else.

## Result

Not run to completion. A 12-step run on Qwen2.5-0.5B-Instruct (2026-09-27, an RTX 4050, about
10 s a step) trained and logged its rollouts; the 500 steps the question needs take about 90
minutes there.
