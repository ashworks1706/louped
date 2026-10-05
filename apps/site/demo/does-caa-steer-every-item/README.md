---
domain: conditioning
status: active
extras: tracking
---

# does-caa-steer-every-item

## Question

CAA's sycophancy vector is meant to make Llama 2 7B Chat agree with the user more when added, and
less when subtracted. Does it move every item that way, or does the mean hide items that move
against it?

## Observation

Contrastive Activation Addition (Rimsky et al., 2024) adds a vector at one layer. The paper reports
the mean effect. Tan et al. (2024) report that steerability varies a lot from item to item.

## Hypotheses

- Most items move with the multiplier: adding the vector raises P(agree).
- Some items move against it, and these share a cause.
- Competing: the vector partly encodes the answer letter, so items move by whether the agreeing
  answer is (A) or (B).

## Baseline

The released results with no vector added (multiplier 0).

## Test

Read the result files the CAA authors committed (layer 13, multipliers -1, 0 and +1, 50 A/B items).
For each item, the slope is (P(agree) at +1 minus P(agree) at -1) / 2. Count the items with a
negative slope, split by the agreeing option. No model runs.

## Stop if

The released files do not list the same items in the same order: the script stops.

## Run

```sh
python experiments/does-caa-steer-every-item/run.py
```

## Result

Mean P(agree) is 0.54 with the vector subtracted, 0.69 with none and 0.62 with it added: at this
layer and strength, adding the vector does not raise the mean. Item by item, 22 of 50 items move
against the multiplier, and 21 of those 22 have the agreeing answer at (A). The mean hides a letter
effect. This is one released run of 50 items, so it is a lead to test on a model we run ourselves.

## Next

Swap the A and B options on every item and re-run the vector. If the slopes follow the letter, the
vector carries the letter.
