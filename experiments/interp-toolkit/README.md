# interp-toolkit

## Question

Where does a chat model tell harmful from harmless requests apart, and do the standard tools
(linear probes, attention patterns, exact and attribution patching, SAE features) agree with each
other and with the refusal direction?

## What would answer it

- Probe accuracy by layer rises well above the majority class at some layer, and the best probe's
  weight vector points the same way as the diff-in-means direction at that layer (cosine well
  above zero).
- Attribution patching correlates strongly with exact residual patching on the same pair, so the
  cheap estimate can be trusted to pick cells to patch exactly.
- With a real SAE at a middle layer, the top features at the last token of a harmful request are
  interpretable (their Feature pages from `loupe features`), and steering on one's decoder row
  changes replies.

## Run

```sh
uv run --all-extras python experiments/interp-toolkit/run.py --tiny   # offline, seconds
uv run --all-extras python experiments/interp-toolkit/run.py          # Qwen2.5-0.5B-Instruct, no SAE
uv run --all-extras python experiments/interp-toolkit/run.py --model google/gemma-2-2b-it \
    --sae-release gemma-scope-2b-pt-res-canonical --sae-id layer_12/width_16k/canonical
```

`--sae-release` also takes a local SAE directory (then omit `--sae-id`). Without an SAE a real
model run skips the SAE part. The prompts, and the `--tiny` planted-refusal toy, are
refusal-direction's. The run appears under Runs with a Figures tab: probe accuracy, attention
(pick the layer and head), exact and attribution patching, SAE features per token and over
positions. The probe direction and the SAE feature are saved under Vectors, ready for Steer and
Ablate or the Playground.

## Result

Qwen2.5-0.5B-Instruct (2026-09-27): probes separate harmful from harmless at 0.91 on layer 0 and
1.00 from layer 6 on; the best probe's cosine with diff-in-means is 0.45. Attribution patching
tracks exact patching at r = 0.80. No SAE was given, so that part was skipped.

`--tiny` (seed 0, the 6-layer toy trained to refuse harmful prompts, 72 prompts, 18 held out):
probe accuracy is 1.0 at every layer, so the task is trivially separable in the toy and the best
layer (0, first of the ties) says nothing; the probe's cosine with diff-in-means there is 0.19.
Attribution and exact patching correlate at 0.994 (Pearson over the layer by position grid); both
put the effect at the last position. The SAE is random (mean L0 128 of 256), so its features only
show the plumbing works. The toy checks mechanics, not claims.
