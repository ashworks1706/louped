# zipy-blackbox

## Question

zipy's v0.7 asks that conditioning on a member's collaboration state moves behaviour while
correctness holds. Does its text conditioning do that on its chat model, seen from outside?

## What would answer it

`run.py` asks 8 org questions, each with what the org's tools returned in the prompt, of zipy's
chat model three ways: no conditioning (baseline), the brief end of the depth dimension, and the
detailed end, as the system prompt line zipy renders
(`apps/engine/cognition/conditioning/text.py`). The grid scores answer length in words (must move)
and whether the answer names the fact from the context (must hold), with paired intervals over
seeds. A verdict of `moved, held` for both conditions answers yes for this model.

zipy's engine has no OpenAI-compatible chat route (its HTTP surface is OAuth, webhooks, platform
events, health and metrics); its chat role is an OpenAI-compatible llama-server, which is what this
talks to.

## Run

In zipy: `just model` (or `just model-gpu`) serves `Qwen/Qwen3-4B-GGUF:Q4_K_M` as `zipy-chat` on
`http://127.0.0.1:8000/v1`. `ZIPY_CHAT_GGUF` swaps the weights, including an adapter from
`experiments/zipy-sft`.

```sh
# ZIPY_BASE_URL (default http://127.0.0.1:8000/v1), ZIPY_API_KEY (default local)
uv run python experiments/zipy-blackbox/run.py
uv run python experiments/zipy-blackbox/run.py --mock      # scripted model, no server
```

## Result

Not run on a real model yet. `--mock` completes the grid (words 7.5, brief 1.5, detailed 19.5;
both `moved, held`).
