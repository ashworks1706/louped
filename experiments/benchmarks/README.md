# benchmarks

## Question

How does a model, a change to it, or a whole system behind an endpoint score on standard
benchmarks, and does a change move that score beyond sample noise? The domain is evaluation.

## What would answer it

One grid per benchmark from inspect_evals: SQuAD (reading, some questions unanswerable), DROP
(reasoning over a paragraph), BFCL (function calling), TruthfulQA (misconceptions) and GSM8K
(maths). The first condition is the baseline; every other condition gets the paired difference per
sample with its 95% interval. Add a benchmark by adding its inspect_evals task and score to
`BENCHMARKS`.

## Run

Any local model, any intervention or adapter through `loupe/`, or any OpenAI-compatible endpoint.
Also from the app: Launch, then `benchmarks/run.py`.

```sh
uv run --all-extras python experiments/benchmarks/run.py --benchmarks squad bfcl --limit 50
uv run --all-extras python experiments/benchmarks/run.py --benchmarks drop \
    --model qwen2.5:7b-instruct --base-url http://localhost:11434/v1
uv run --all-extras python experiments/benchmarks/run.py --benchmarks truthfulqa \
    --conditions '{"ablated": {"interventions": {"kind": "ablate", "vector": "<v>"}}}'
```

Datasets download from the Hugging Face Hub on first use.

## Result

Not run on a real model yet.
