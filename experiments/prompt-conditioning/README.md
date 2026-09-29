# prompt-conditioning

## Question

Does a line of conditioning in the system prompt move how a model answers while what it answers
holds? The domain is conditioning (docs/ARCHITECTURE.md): the cheapest way to steer a model is a
sentence of instruction, and the baseline a steering vector or a soft prompt has to beat.

## What would answer it

`run.py` asks 8 questions, each with the context that answers it, three ways: no system line
(baseline), a brief instruction and a detailed one (`--instructions` sets your own). The grid scores
answer length in words (should move) and whether the answer names the fact from the context
(should hold), with paired intervals over seeds. A verdict of `moved, held` for a condition says the
line steers style without costing accuracy on that model.

## Run

Any model: a local one through `loupe/` (the default, no server), or any OpenAI-compatible server
(vLLM, llama.cpp, Ollama, your own system's API). Also from the app: Launch, then
`prompt-conditioning/run.py`.

```sh
uv run --all-extras python experiments/prompt-conditioning/run.py
uv run --all-extras python experiments/prompt-conditioning/run.py \
    --model qwen2.5:7b-instruct --base-url http://localhost:11434/v1
uv run --all-extras python experiments/prompt-conditioning/run.py \
    --instructions '{"formal": "Answer formally.", "casual": "Answer casually."}'
uv run --all-extras python experiments/prompt-conditioning/run.py --mock    # offline wiring
```

## Result

On qwen2.5:7b-instruct through Ollama (one seed, 2026-09-27): about 32 words with no line, 8 with
the brief one and 101 with the detailed one; correctness 0.88 in all three. The line moves length
by an order of magnitude and leaves correctness where it was. On Qwen2.5-0.5B-Instruct locally (one
seed): 87 words with no line, 4 brief, 47 detailed; correctness 0.75, 0.62, 0.62, so on the small
model both lines cost a question. `--mock` completes the grid (words
7.5, brief 1.5, detailed 19.5; both `moved, held`).
