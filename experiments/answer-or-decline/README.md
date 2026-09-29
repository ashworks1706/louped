# answer-or-decline

## Question

Does a system answer what it can know and decline what it cannot? And does what you built around a
model (retrieval, tools, an agent loop) do better at both than the model alone? The domain is
evaluation science on black-box endpoints (docs/ARCHITECTURE.md).

## What would answer it

`run.py` asks 13 questions: 9 with a fixed answer and 4 no system can know (what the asker is
thinking, what they ate). An answerable question scores 1 when the reply names a gold answer; an
unanswerable one scores 1 when the reply declines. With `--compare-model`, the grid pairs the
system against it per question, with an interval over the paired difference: whether the system
beats what it is built on beyond sampling noise.

## Run

Any model or endpoint, the system and what to compare it with alike. Also from the app: Launch,
then `answer-or-decline/run.py`.

```sh
uv run --all-extras python experiments/answer-or-decline/run.py                 # a local model
uv run --all-extras python experiments/answer-or-decline/run.py \
    --model my-agent --base-url http://localhost:8080/v1 --cut 'Sources:' \
    --compare-model qwen2.5:7b-instruct --compare-base-url http://localhost:11434/v1
uv run --all-extras python experiments/answer-or-decline/run.py --questions my-questions.jsonl
```

`--questions` takes JSONL lines of `{"question": "...", "answers": ["..."]}`; leave `answers`
empty for a question that should be declined.

## Result

On an earlier version of this set (2026-09-27), Qwen2.5-0.5B-Instruct locally and
qwen2.5:7b-instruct through Ollama both scored 1.00: every fact named, every unknowable question
declined. The built-in set does not separate them; a harder `--questions` set is the next step.
