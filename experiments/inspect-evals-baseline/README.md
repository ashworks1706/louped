# inspect-evals-baseline

## Question

Does an inspect_evals benchmark run through the `loupe/` provider score what the model's authors
report, so loupe's numbers can be trusted; and what does an intervention cost on it?

## What would answer it

inspect_evals `gsm8k` (the 1319 test problems, greedy, exact numeric match on the ANSWER line):

- Base: accuracy within noise of the reported number. With 1319 samples the standard error is
  about 1.4 points at 50% and 1.2 at 73%, so within about 2.5 to 3 points of it.
- Intervened (by default the refusal direction of experiments/refusal-direction, ablated
  everywhere): the paired difference to base in the grid. Arditi et al. (2024) report that
  removing the refusal direction leaves capability benchmarks, GSM8K among them, mostly
  unchanged, so the interval should sit near zero.

The reported numbers are 49.6 for Qwen2.5-0.5B-Instruct and 73.2 for Qwen2.5-1.5B-Instruct (the
Qwen2.5 release, qwenlm.github.io/blog/qwen2.5-llm, and arXiv:2412.15115).

Qwen's own harness and prompt are not published with the table (their base models are scored
4-shot), so a gap of a few points beyond noise can be the prompt rather than loupe. The first
check then is `--fewshot 0` or `--fewshot 4`, and the parse failures in the samples.

## Run

On a GPU box, after `experiments/refusal-direction/run.py` has saved the direction:

```sh
uv run --all-extras python experiments/inspect-evals-baseline/run.py
```

It runs base and intervened as one grid (Runs, the grid run: accuracy per condition and the
paired difference against base with its 95% interval, each cell linking to its samples) and prints
one line per condition with accuracy, standard error, the reported number and whether the two are
within 1.96 standard errors. For the comparison with the reported number, pin the weights with
`--revision <commit>` (the Hub commit of the model) and record it with the result, so a rerun reads
the same model. `--limit 50` is a smoke run; `--intervention None` runs the base only;
`--model Qwen/Qwen2.5-1.5B-Instruct --intervention '<spec>'` needs a vector saved for that model.
Generation is one sample at a time and greedy, so the whole split takes a while per condition.

The same task from the Inspect command line, for any other inspect_evals benchmark too:

```sh
uv run --all-extras inspect eval inspect_evals/gsm8k --model loupe/Qwen/Qwen2.5-0.5B-Instruct \
    --max-tokens 512 --log-dir .loupe/logs -M revision=<commit> \
    -M interventions='{"kind": "ablate", "vector": "refusal.qwen2.5-0.5b-instruct"}'
```

## Result

Qwen2.5-0.5B-Instruct on the first 50 test questions (2026-09-27, 10-shot, greedy): 0.38 ± 0.07
against the reported 0.496, within noise; with the refusal direction ablated, 0.34. The full split
is the acceptance test.
