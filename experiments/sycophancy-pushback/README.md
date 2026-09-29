# sycophancy-pushback

## Question

When a chat model gives a right answer and then drops it because the user pushes back with a wrong
one and no evidence, is that carried by a direction in the residual stream at the pushback turn?
Does removing it make the model hold, without costing turn 1 correctness?

## What would answer it

On TriviaQA questions from Sharma et al.'s are_you_sure set: among samples right at turn 1, held
at turn 2 rises under the ablated or subtracted direction beyond seed and sample variance (the
grid's paired interval excludes zero), while turn 1 correctness does not drop (verdict "moved,
held"). Patching locates where the pushed answer enters.

## Run

```sh
uv run --all-extras python experiments/sycophancy-pushback/run.py            # Qwen2.5-0.5B-Instruct
uv run --all-extras python experiments/sycophancy-pushback/run.py --tiny     # offline, a minute
```

The analysis run (layer scores, pushback outcomes, patching) and the grid run appear under Runs;
the direction under Vectors as caving.<model>. Every grid cell opens its eval samples.

## Result

Qwen2.5-0.5B-Instruct (2026-09-27): of the questions it answered right first, 32 caved under
pushback and 52 held. The best caving direction sat at layer 1, too early to be a mechanism worth
claiming; a 1.5B to 3B model is the next step.

`--tiny` trains a toy to cave on half the questions. The pipeline recovers the planted split
(5 caved, 5 held) and the grid runs; the toy's numbers are not evidence about real models.
