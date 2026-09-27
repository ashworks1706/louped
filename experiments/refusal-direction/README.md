# refusal-direction

## Question

Is refusal in a chat model mediated by a single direction in the residual stream (Arditi et al.,
2024), and does loupe recover it: ablating it stops refusals, adding it causes them?

## What would answer it

On held-out prompts from the paper's splits: harmful refusal rate falls near zero with the
direction ablated everywhere, harmless refusal rate rises near one with it added at its layer.

## Run

```sh
uv run --extra interp python experiments/refusal-direction/run.py            # Qwen2.5-0.5B-Instruct
uv run --extra interp python experiments/refusal-direction/run.py --tiny     # offline, seconds
```

Then `eval.py` (same flags) runs the test prompts through Inspect twice via the `loupe/`
provider, base and with the direction ablated; select both under Runs and Compare them.

The run appears under Runs with a Figures tab (per-layer scores, examples, logit lens, patching),
and the direction under Vectors.

## Result

Not yet run on a real model: this environment cannot reach huggingface.co.

`--tiny` trains a 6-layer toy to refuse the harmful prompts first. With seed 0 it reproduces the
shape of the claim (harmful 100% to 0% refusal ablated, harmless 0% to 100% added). Across seeds
0 to 5 it holds fully on one and only halfway (ablation or addition, not both) on the other five, so the toy only shows the
pipeline works; it is not evidence about real models. On seed 0 the Inspect eval agrees with the
analysis: harmful refusal 1.0 base, 0.0 ablated; harmless 0.0 in both.
