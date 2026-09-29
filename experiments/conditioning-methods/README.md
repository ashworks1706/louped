# conditioning-methods

## Question

To make a model answer in one word, how do three ways of conditioning it compare: a line in the
system prompt (no parameters), a rank-4 ReFT intervention on one layer (a few thousand parameters,
pyreft) and a LoRA (millions)? Does each shorten the answers on countries it never saw, and what
does each cost in correctness? The domain is conditioning (docs/ARCHITECTURE.md), with adapters.

## What would answer it

30 capital-city questions answered with the name alone train ReFT and LoRA; 15 more countries are
the test. On the test: words per answer (should fall toward 1) and whether the answer names the
capital (should hold). The grid pairs base, the prompt line and the LoRA per question; ReFT's
training run holds the same two scores for base and ReFT on the same 15 questions, with every
reply side by side.

## Run

```sh
uv run --all-extras python experiments/conditioning-methods/data.py
uv run --all-extras loupe train reft experiments/conditioning-methods/reft.yaml
uv run --all-extras loupe train sft experiments/conditioning-methods/sft.yaml
uv run --all-extras python experiments/conditioning-methods/eval.py
```

ReFT trains in pyreft's own environment, which uv builds on first use. All four steps are on the
Launch page, the configs editable there.

## Result

Not run yet.
