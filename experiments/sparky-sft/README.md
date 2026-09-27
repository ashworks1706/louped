# sparky-sft

## Question

Does fine-tuning SparkyAI's Qwen3-4B on its own reviewed Discord turns improve its tool routing and
grounding on SparkyAI's golden cases?

## What would answer it

SparkyAI's regression gate (`just eval run` then `just eval compare` in the SparkyAI repo) with
`SPARKY_CHAT_GGUF` set to the exported file, against the committed baseline.

## Run

Everything is local: spans from your self-hosted Phoenix (`just phoenix` in SparkyAI), a model
from the Hugging Face Hub (no token for Qwen3), your GPU. Set `PHOENIX_API_KEY` only if your
Phoenix has auth turned on.

```sh
loupe data export --name sparky-sft --source phoenix --url http://127.0.0.1:6006 \
    --project sparky --redact-extra asu-id
loupe data verify --name sparky-sft
loupe data review --name sparky-sft
loupe data curate --name sparky-sft
loupe train sft experiments/sparky-sft/sft.yaml     # GGUF export needs a CUDA GPU and unsloth
```

Then in SparkyAI: `SPARKY_CHAT_GGUF=$LOUPE_HOME/checkpoints/sparky-sft/gguf/<file>.gguf just model`.

## Result

Not run yet. Migrated from `SparkyAI/apps/training` (datasets, posttrain) on 2026-09-27. Two
changes from the original: examples now go through a human review ledger as zipy's did, and the
ASU-id redaction actually fires (the phone pattern used to catch every 10-digit id first).
