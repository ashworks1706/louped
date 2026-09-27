# piramid-blackbox

## Question

piramid v0.6 puts retrieval inside the decoder and is measured against v0.5, plain RAG on an
unmodified model. How much does that baseline gain on the model piramid serves, and does retrieval
inside the model (loupe's Inject on the same checkpoint) reach it?

## What would answer it

`run.py` asks 8 questions about a made-up station, answerable only from 8 passages built into it.
piramid's `/v1/chat/completions` serves its model without retrieval, so BM25 runs here and puts the
top k passages in the prompt (`loupe.inspect_ext.rag`). Conditions: closed book (baseline) and RAG
through piramid; with `--inject-layer N`, the same checkpoint run locally with the passages
injected at layer N. Scored on F1, exact match and recall@k, with the paired interval of each
condition against closed book.

## Run

In piramid: build with `--features inference-candle`, download `Qwen/Qwen2.5-0.5B-Instruct`, and
`piramid serve --config piramid.yaml` with `runtime.inference.enabled: true` (README quickstart).
It listens on `127.0.0.1:6333`; the model id is `inference.model_name`, else the model directory
name.

```sh
# PIRAMID_BASE_URL (default http://127.0.0.1:6333/v1), PIRAMID_API_KEY (piramid's key, if set)
uv run --extra rag python experiments/piramid-blackbox/run.py
uv run --extra rag python experiments/piramid-blackbox/run.py --inject-layer 12
uv run --extra rag python experiments/piramid-blackbox/run.py --mock   # scripted model
```

## Result

Not run on a real server yet. `--mock --inject-layer 6` completes the grid (closed 0.00, rag and
inject 1.00, moved); BM25 puts the gold passage first for all 8 questions.
