# regression-cases

## Question

Does a change to a system (a fine-tune, a new prompt, another model, a new release of an agent)
keep what its own cases require: the right tool with the right arguments, the right source cited,
the facts it must state, the things it must never say, and declining what it cannot know?

## What would answer it

A grid over the conditions on `expectations/mean`: per case, the share of its expectations met,
each check itemized on the sample. Every condition is paired against the first, case by case, so a
regression shows as a negative interval and the cases behind it are one click away.

## Run

Cases are a JSONL file (`example.jsonl` shows the format; the expectations are in
`loupe.inspect_ext.cases`). The system can be a local model, any OpenAI-compatible endpoint, or an
agent that runs its own tools and reports them in a `trace` field on its reply (`--agent`, see
`loupe.inspect_ext.agent`).

```sh
uv run --all-extras python experiments/regression-cases/run.py
uv run --all-extras python experiments/regression-cases/run.py --cases my-cases.jsonl \
    --model my-agent --base-url http://localhost:8080/v1 --agent
uv run --all-extras python experiments/regression-cases/run.py --cases my-cases.jsonl \
    --conditions '{"tuned": {"model": "loupe/my-finetune"}}'
```

## Result

Not run on a real system yet. The agent path is covered by a test against a local HTTP agent.
