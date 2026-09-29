# intercode-ctf

## Question

Does a published agentic benchmark run end to end through the `loupe/` provider, in its own
Docker sandbox, so any agent eval in inspect_evals can be run base and under an intervention?

## What would answer it

inspect_evals `gdm_intercode_ctf`: the 78 InterCode-CTF tasks (picoCTF challenges) that need no
internet, as used in Google DeepMind's dangerous-capability evaluations (Phuong et al., 2024,
arXiv:2403.13793). Each sample gets a fresh Ubuntu container without network, holding the task's
files; the agent is Inspect's react with bash and python tools and up to three submissions,
scored by whether the answer contains the flag.

The acceptance is mechanical: every sample finishes (no provider or sandbox errors), tool calls
parse and run, and the transcripts read in the UI. No solve rate for Qwen2.5 at this size is
published; expect a low one. With `--intervention`, the steered run pairs with the base in
Compare.

## Run

Needs Docker (the first run builds the image, a few minutes) and a GPU for reasonable time. The
dataset comes from princeton-nlp/intercode on GitHub, cached by inspect_evals.

```sh
uv run --all-extras python experiments/intercode-ctf/run.py --limit 5    # smoke run
uv run --all-extras python experiments/intercode-ctf/run.py              # all 78 tasks
uv run --all-extras python experiments/intercode-ctf/run.py \
    --intervention '{"kind": "steer", "vector": "<a saved vector>", "alpha": 4}'
```

The default model is Qwen/Qwen2.5-1.5B-Instruct (`--model` for another; `--revision <commit>`
pins its Hub weights, which a reported number should record). Base and intervened run as one grid
that prints its run id: solve rate per condition and the paired difference against base, each cell
linking to its eval samples. Open a sample for its tool calls and results, or its Inspect tab for
Inspect View.

The same from the Inspect command line:

```sh
uv run --all-extras inspect eval inspect_evals/gdm_intercode_ctf \
    --model loupe/Qwen/Qwen2.5-1.5B-Instruct --max-tokens 1024 --log-dir .loupe/logs
```

## Result

Qwen2.5-1.5B-Instruct on the first five tasks (2026-09-27): one solved, 0.20.
