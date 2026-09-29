# tool-rl

## Question

Does GRPO in a tool environment teach a small instruct model to use a calculator and submit an
answer, raising its accuracy on arithmetic it gets wrong unaided?

## What would answer it

The environment's reward (`rewards/Calculator`, 1 for a correct submit) rising over steps, and the
Rollouts figure showing calculate and submit calls in the last step where the first had none or
malformed ones. A second reward, `rewards/stated`, gives half credit for a correct number in the
reply's text: Qwen3-0.6B at first answers in text and never submits, so without it every rollout
scores 0 and GRPO learns nothing (loss and gradient exactly 0 in a first real run). Test
accuracy, base against trained, through the loupe/ provider with the same tools, compared in
Compare.

## Run

Needs a GPU for reasonable time; everything is local and the data is generated offline.

```sh
uv run --all-extras python experiments/tool-rl/data.py
loupe train grpo experiments/tool-rl/grpo.yaml --dry-run
loupe train grpo experiments/tool-rl/grpo.yaml
```

## Result

Not run to completion yet. A 6-step smoke run on an RTX 4050 (2026-09-27) found the flat reward
that `stated` fixes: tools were called in 75-84% of rollouts, submit in none.
