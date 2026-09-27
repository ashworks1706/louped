# refusal-finetuning

## Question

When a chat model is fine-tuned to comply with harmful requests, does refusal go because the
refusal direction goes (the model stops writing it), or because the model routes around a
direction that is still there?

## What would answer it

Across DPO checkpoints: the harmful refusal rate, and the mean projection of the harmful prompts'
last token onto the refusal direction at its layer. Then the base against the final model, per
layer: residual cosine, and the cosine between their harmful-minus-harmless directions.

- Projection falls with the refusal rate: the feature is suppressed.
- Refusal falls while the projection and the direction cosine hold: it is bypassed downstream.

## Run

```sh
uv run --all-extras python experiments/refusal-direction/run.py          # saves the direction
uv run --all-extras python experiments/refusal-finetuning/run.py
uv run --all-extras python experiments/refusal-finetuning/run.py --tiny --steps 20 --save-every 5  # offline, the run quoted below
```

The preference pairs are the model's own replies: chosen with the direction ablated, rejected
without, so no harmful text is brought in. The DPO run shows its loss and reward margins under
Runs; the dynamics run shows both measures against step and the model diff by layer.

## Result

Not yet run on a real model: this environment cannot reach huggingface.co.

`--tiny` (seed 0, the planted-refusal toy, 12 pairs, 20 steps, a checkpoint every 5): the harmful
refusal rate goes 1.0, 0.0, 0.0, 0.0, 0.0 and the projection 7.06, 0.01, -0.88, -1.20, -1.27, so in
the toy the direction itself is written away within five steps. The toy has one planted mechanism,
so this checks the pipeline, not the claim.
