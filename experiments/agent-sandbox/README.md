---
domain: agents
status: parked
---

# agent-sandbox

## Question

Does a small instruct model find and report a planted value with bash in a sandbox, and does an
intervention (a steering vector) change how it uses its tools?

## What would answer it

Accuracy (the submitted word), base against steered, paired in Compare; and in the transcripts,
how many tool calls each takes and how many fail to parse.

## Run

Needs Docker. Every sample starts a fresh `python:3.12-slim` container with no network.

```sh
uv run --all-extras python experiments/agent-sandbox/run.py --model Qwen/Qwen2.5-1.5B-Instruct \
    --steer '{"kind": "steer", "vector": "<a saved vector>", "alpha": 4}'
inspect eval experiments/agent-sandbox/task.py --model loupe/Qwen/Qwen2.5-1.5B-Instruct
```

Open a sample under Runs: each tool call shows its arguments, and each result or error sits under
the call it answers.

## Result

Qwen2.5-1.5B-Instruct (2026-09-27, one seed): accuracy 0.33, one of the three planted words found and
submitted.
