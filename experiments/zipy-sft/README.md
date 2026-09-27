# zipy-sft

## Question

Does fine-tuning zipy's chat model on its own reviewed tool-calling turns make it pick the right
tool and arguments more often than the base model, without hurting the rest?

## What would answer it

zipy's own regression evals (`just eval` in the zipy repo) on the fine-tuned model against the base,
per case. Loss going down here says only that training ran.

## Run

Everything is local: traces from your own zipy, a model from the Hugging Face Hub (no token for
Qwen3), your GPU. Nothing needs an API key.

```sh
loupe data export --name zipy-sft --source traces --path ../zipy/.zipy/traces
loupe data verify --name zipy-sft
loupe data review --name zipy-sft          # decisions land in experiments/zipy-sft/decisions.jsonl
loupe data curate --name zipy-sft
loupe train sft experiments/zipy-sft/sft.yaml --dry-run
loupe train sft experiments/zipy-sft/sft.yaml
```

The adapter lands in `$LOUPE_HOME/checkpoints/zipy-sft/adapter`; point zipy's `[models.chat]` at
a server that loads it. The run shows under Runs with its loss curve.

## Result

Not run yet: no traces have been reviewed. Migrated from `zipy/apps/testbed` (datasets, curation,
posttrain) on 2026-09-27.
