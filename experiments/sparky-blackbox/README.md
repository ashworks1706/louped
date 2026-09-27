# sparky-blackbox

## Question

Does SparkyAI's agent (retrieval, live search and tools around its Qwen3-4B) answer ASU questions
better than the same model asked directly, and does it decline what it cannot know?

## What would answer it

`run.py` asks 13 questions (10 with a stable gold answer, 3 no public source can answer) of two
OpenAI-compatible endpoints, and scores each on naming a gold answer or, for the last three, on
declining. The baseline is the bare model on SparkyAI's llama-server; the condition is the engine,
whose `/v1/chat/completions` runs one agent turn (`apps/engine/src/routes/openai.rs`). The engine's
appended `Tools:` and `Sources` blocks are cut before scoring. The grid gives the paired interval of
engine minus model. Black box: it scores answers, not the passages the engine retrieved; recall
and faithfulness of the engine's retrieval are for SparkyAI's own evals.

## Run

In SparkyAI: `just infra`, `just model`, `just migrate`, `just engine` (`.env` from `.env.example`).
The engine listens on `SPARKY_APP__HTTP_ADDR` (default `0.0.0.0:8080`) and takes
`SPARKY_ENGINE__SERVICE_TOKEN` as its bearer key; llama-server serves the model on `:8000`.

```sh
export SPARKY_API_KEY=<SPARKY_ENGINE__SERVICE_TOKEN>        # default change-me
# SPARKY_BASE_URL (default http://localhost:8080/v1), LLAMA_BASE_URL (http://localhost:8000/v1)
uv run python experiments/sparky-blackbox/run.py
uv run python experiments/sparky-blackbox/run.py --mock     # scripted models, no servers
```

Each run sends a fresh `user`, which the engine requires and keys its conversation memory by.

## Result

Not run on a real engine yet. `--mock` completes the grid (model 0.46, engine 0.92, moved).
