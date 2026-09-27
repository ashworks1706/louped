# coding-agent

## Question

Does a coding agent pass hidden unit tests more often under one condition than another (base
against steered, one model against another, a product endpoint), and does its tool use change with
it: how many calls it makes, how many fail, whether it runs its code before submitting?

## What would answer it

A grid over the conditions on `verify/accuracy` (hidden tests, inspect_evals' HumanEval scorer),
with the tool-use scorers from `loupe.inspect_ext` beside it on every run: `tool_calls/mean`,
`tool_errors/mean` (parse failures included), `called/mean` (python was used) and
`grounded/mean` (the submitted answer contains what a successful python run printed). Any of them
can be the grid's metric, with accuracy as `--held`.

## Run

Needs Docker. Every sample starts a fresh `python:3.12-slim` container with no network; the agent
is Inspect's react with bash and python in it, and the tests run in the same container after submit.
`--benchmark humaneval` swaps the four builtin problems for HumanEval (downloaded from the Hub).

```sh
uv run --all-extras python experiments/coding-agent/run.py --scripted      # checks the plumbing
uv run --all-extras python experiments/coding-agent/run.py --model Qwen/Qwen2.5-1.5B-Instruct \
    --conditions '{"base": {}, "steered": {"interventions": {"kind": "steer", "vector": "<v>", "alpha": 4}}}'
LOCAL_BASE_URL=http://localhost:8080/v1 LOCAL_API_KEY=x uv run --all-extras python \
    experiments/coding-agent/run.py --conditions '{"loupe": {}, "local": {"model": "openai-api/local/qwen"}}'
uv run --all-extras python experiments/coding-agent/run.py --metric tool_errors/mean --held verify/accuracy
inspect eval experiments/coding-agent/task.py --model loupe/Qwen/Qwen2.5-1.5B-Instruct
```

## Result

Not yet run on a real model: this environment cannot reach huggingface.co.

`--scripted` (two mock agents: one runs its solution in python and submits it, one calls python
with a wrong argument and submits a stub), in Docker: careful 1.0 accuracy, 0.0 tool errors; sloppy
0.0 accuracy, 1.0 tool errors, verdict "moved, broke" on `tool_errors/mean` held on accuracy. The
same task through `loupe/` on the tiny model with scripted replies scored 1.0, so the provider's
tool calls reach the sandbox and the hidden tests.
