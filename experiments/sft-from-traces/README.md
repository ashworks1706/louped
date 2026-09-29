# sft-from-traces

## Question

Does fine-tuning a model on its own system's reviewed conversations (the turns a person kept, or
fixed) make it better at that system's job, such as picking the right tool and arguments, without
hurting the rest? The domain is small models and data (docs/ARCHITECTURE.md).

## What would answer it

The same eval on the fine-tuned model and the base, paired per sample: the system's own regression
cases as an Inspect task, run as a grid with conditions `base` and `tuned`
(`{"model": "loupe/sft-from-traces"}`), with a held score for what must not get worse. Loss going
down here says only that training ran.

## Run

Everything is local. Pick where the conversations come from:

- Trace files: any system that logs a JSONL line
  `{"event": "generation", "data": {"input": [...messages], "output": "...", "tool_calls": [...]}}`
  per model call, anywhere under a folder.
- OpenTelemetry spans in Phoenix: any system instrumented with OpenInference or the OTel GenAI
  conventions and sending to a self-hosted Phoenix. `--span-kind` names the attribute that marks a
  model call when yours is not OpenInference's; set `PHOENIX_API_KEY` if Phoenix has auth on.
- **A teacher model**, when there are no logs yet: `loupe data collect` asks any Inspect model each
  of your prompts (distillation).

```sh
loupe data export --name sft-from-traces --source traces --path path/to/traces
loupe data export --name sft-from-traces --source phoenix --url http://127.0.0.1:6006 \
    --project my-app --redact-extra id-10
loupe data collect --name sft-from-traces --prompts prompts.jsonl --teacher loupe/Qwen/Qwen2.5-7B-Instruct

loupe data verify --name sft-from-traces
loupe data review --name sft-from-traces   # decisions land in experiments/sft-from-traces/decisions.jsonl
loupe data curate --name sft-from-traces
loupe train sft experiments/sft-from-traces/sft.yaml --dry-run
loupe train sft experiments/sft-from-traces/sft.yaml
```

Export redacts emails, phone numbers, platform ids and leaked tokens; `--redact-extra` adds `id-10`
(a lone 10-digit id) or any regex. In the app, export, verify, curate and train are on the Launch
page; review is interactive and runs in a terminal.

The adapter lands in `$LOUPE_HOME/checkpoints/sft-from-traces/adapter`, and the merged model under
`$LOUPE_HOME/models/sft-from-traces`, so `loupe/sft-from-traces` works in evals, grids and the
Playground. The run shows under Runs with its loss curve.

## Result

Not run on real traces yet. The recipe runs end to end in 4-bit on a 6 GB GPU (256 GSM8K examples,
loss 0.70 to 0.40 in 40 steps, the merged model served through `loupe/`).
