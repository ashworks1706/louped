# refusal-direction

## Question

Is refusal in a chat model mediated by a single direction in the residual stream (Arditi et al.,
2024), and does loupe recover it: ablating it stops refusals, adding it causes them?

## What would answer it

On the paper's held-out prompts: harmful refusal rate falls near zero with the direction ablated
everywhere, harmless refusal rate rises near one with it added at its layer.

Expected, from the paper (arXiv:2406.11717): on all 13 chat models, Qwen 1.8B to
72B among them, ablation drops refusal on JailbreakBench's 100 harmful instructions to near zero,
and addition makes the model refuse most harmless Alpaca instructions. The authors' released run
for their smallest Qwen (`pipeline/runs/qwen-1_8b-chat` in andyrdt/refusal_direction), with the
same substring judge over 512 tokens: harmful refusal 70% to 1% ablated, harmless 3% to 98% added,
direction at layer 15 of 24. Qwen2.5 is not in the paper, so the claim to reproduce is that shape,
not those exact numbers.

## Data and method

Train and val prompts come from the paper's splits (128 and 32 of each kind), harmful test prompts
are JailbreakBench's 100, and harmless test prompts 100 from the harmless test split, all
downloaded once from andyrdt/refusal_direction on GitHub into `LOUPE_HOME/data`. As in the
paper, train and val keep only prompts the model already treats as their kind, the candidate
layers are the first 80%, and refusal is judged by its substring list. Differences: one position
(the last token) instead of the paper's search over the post-instruction tokens, and no KL filter
on the chosen direction.

## Run

On a GPU box, from the repo root (the model and data download on first use):

```sh
uv run --all-extras python experiments/refusal-direction/run.py --max-new-tokens 512
uv run --all-extras python experiments/refusal-direction/eval.py --max-tokens 512
uv run --all-extras loupe serve
```

`run.py` defaults to Qwen/Qwen2.5-0.5B-Instruct (`--model Qwen/Qwen2.5-1.5B-Instruct` for
another) and prints the chosen layer and the four refusal rates. It saves the direction as
`refusal.qwen2.5-0.5b-instruct`. `eval.py` runs the same test prompts through Inspect twice via the
`loupe/` provider, base and with the direction ablated. In the UI: the analysis run under Runs
has a Figures tab (per-layer scores, examples, logit lens, patching), the direction is under
Vectors, and the two eval runs selected under Runs open in Compare.

`--tiny` (both scripts) runs offline in minutes on a toy model trained to refuse.

## Result

Qwen2.5-0.5B-Instruct (2026-09-27): the direction is at layer 13. Ablated, harmful refusal goes
from 73% to 0%; added, harmless refusal from 9% to 98%. The Inspect evals agree: harmful 0.73 to
0.00, and a paired difference of -0.40 over all 200 prompts, interval [-0.47, -0.34].

`--tiny` trains a 6-layer toy to refuse the harmful prompts first. With seed 0 it reproduces the
shape of the claim (harmful 100% to 0% refusal ablated, harmless 0% to 100% added). Across seeds
0 to 5 it holds fully on one and only halfway (ablation or addition, not both) on the other five,
so the toy only shows the pipeline works; it is not evidence about real models. On seed 0 the
Inspect eval agrees with the analysis: harmful refusal 1.0 base, 0.0 ablated; harmless 0.0 in
both.
