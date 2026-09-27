# tool-rl

## Question

Does GRPO in a tool environment teach a small instruct model to use a calculator and submit an
answer, raising its accuracy on arithmetic it gets wrong unaided?

## What would answer it

The environment's reward (`rewards/Calculator`) rising over steps, and the Rollouts figure showing
calculate and submit calls in the last step where the first had none or malformed ones. Test
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

Not yet run: this environment cannot reach huggingface.co. The recipe is covered by the test
suite on a tiny model.
