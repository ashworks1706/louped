# retrieval-injection

## Question

How much does a model gain from retrieved passages placed in its prompt (plain RAG), and does
retrieval inside the model, the same passages injected into its residual stream at one layer with
no prompt text, reach that gain? The domain is retrieval inside the model (docs/ARCHITECTURE.md).

## What would answer it

`run.py` asks 8 questions about a made-up station, answerable only from 8 passages built into it.
BM25 puts the top k passages in the prompt (`loupe.inspect_ext.rag`). Conditions: closed book
(baseline), RAG in the prompt, and with `--inject-layer N` the same checkpoint with the passages
injected at layer N. Scored on F1, exact match and recall@k, with the paired interval of each
condition against closed book. Inject reaching RAG's F1 says the state carries what the text did.

## Run

The default runs every condition locally on Qwen2.5-0.5B-Instruct. Closed book and RAG can instead
run on any OpenAI-compatible server (a serving stack with its own retrieval, say), with inject on
the same weights locally through `--checkpoint`. Also from the app: Launch, then
`retrieval-injection/run.py`.

```sh
uv run --all-extras python experiments/retrieval-injection/run.py --inject-layer 12
uv run --all-extras python experiments/retrieval-injection/run.py \
    --model Qwen2.5-0.5B-Instruct --base-url http://127.0.0.1:6333/v1 \
    --inject-layer 12 --checkpoint Qwen/Qwen2.5-0.5B-Instruct
uv run --all-extras python experiments/retrieval-injection/run.py --mock --inject-layer 6
```

## Result

Qwen2.5-0.5B-Instruct, `--inject-layer 12` (2026-09-27): closed book F1 0.01, RAG in the prompt
0.46, injected at layer 12 0.00 with recall 1.00. The passages reach the prompt and help; injected
state at one mid layer carries none of it on this model, so the next question is which layer, if
any, does. `--mock --inject-layer 6` completes the grid (closed 0.00, rag and
inject 1.00, moved); BM25 puts the gold passage first for all 8 questions.
