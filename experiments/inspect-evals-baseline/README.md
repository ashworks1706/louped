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

Reported, from the Qwen2.5 release (qwenlm.github.io/blog/qwen2.5-llm, table "Qwen2.5-0.5B/1.5B-Instruct
Performance"; the same numbers in the Qwen2.5 technical report, arXiv:2412.15115):

| Model | GSM8K |
|---|---|
| Qwen/Qwen2.5-0.5B-Instruct | 49.6 |
| Qwen/Qwen2.5-1.5B-Instruct | 73.2 |

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

Not yet run on a real model: this environment cannot reach huggingface.co. Offline, with the
GSM8K splits read from openai/grade-school-math on GitHub instead of the Hub and the tiny test
model with a random direction ablated, both runs complete through the provider, are logged under
LOUPE_HOME with their condition tags and share sample ids, so Compare pairs them. A missing vector
fails before the base run starts.
