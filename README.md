<p align="center"><img src="docs/brand/wordmark.svg" alt="loupe" height="48"></p>
<p align="center">A local testbed for research on LLM behavior and efficiency.</p>

<p align="center">
  <a href="apps/site/content/docs/domains.mdx">Domains</a> •
  <a href="docs/ARCHITECTURE.md">Architecture</a> •
  <a href="docs/ROADMAP.md">Roadmap</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

loupe is where research questions about language models get answered. It studies two things:

- **Behavior and alignment**: what models do, and why.
- **Efficiency and systems**: what it costs to run them.

Each question is an experiment: a folder in `experiments/` with a stated question, the observation
behind it, competing hypotheses, a baseline, a controlled test, a stop condition and a result. The
app shows which questions are active, launches their runs and reads every result back, sample by
sample. Everything runs on one machine, on open-weight models, with no hosted model and no API key.

## The method

Every experiment uses the same three steps on the same model:

1. **Change it.** Steer or ablate a direction, ablate attention heads, inject retrieved state at a
   layer, fine-tune it (SFT, DPO, GRPO, ReFT, LoRA), rewrite its prompt, add adapters, swap its
   attention kernel.
2. **Measure what changed.** The same Inspect evals run on the base and the changed version, paired
   per sample, over seeds, with bootstrap intervals and a verdict on what moved and what held.
3. **Explain it.** Logit lens, activation and attribution patching, probes, attention, SAE
   features and attribution graphs, on the model under the change.

A change is one spec, a policy, that runs the same way in an eval, a training run, the Playground
and an analysis. Systems that are not open weights come in as an OpenAI-compatible endpoint, an
agent endpoint or logged model calls.

## Domains

| Axis | Domain | Experiments |
|---|---|---|
| Behavior & alignment | Mechanisms | `refusal-direction`, `refusal-finetuning`, `interp-toolkit`, `attention-heads` |
| | Sycophancy and honesty | `sycophancy-pushback`, `answer-or-decline` |
| | Steering and conditioning | `prompt-conditioning`, `conditioning-methods` |
| | Agent behavior | `coding-agent`, `agent-sandbox`, `intercode-ctf`, `regression-cases`, `tool-rl` |
| Efficiency & systems | Context and retrieval inside the model | `retrieval-injection` |
| | Inference cost and kernels | `attention-kernels` |
| | Small and specialised models | `diffusion-adapters`, `sft-from-traces` |
| Instrument checks | Reproducing known results | `inspect-evals-baseline`, `benchmarks`, `gsm8k-grpo` |

Instrument checks are not research questions: they show loupe reaches reported numbers, so a
result on either axis can be trusted.

## Results so far

All on Qwen2.5-0.5B-Instruct (2026-09-27), so small-model results, not claims about larger ones.
The full numbers, setup and caveats are in each experiment's README.

- **Refusal is one direction** (`refusal-direction`). At layer 13; ablated, harmful refusal goes
  from 73% to 0%, paired difference -0.40 [-0.47, -0.34] over 200 prompts. Added, harmless refusal
  goes from 9% to 98%.
- **Fine-tuning to comply suppresses that direction rather than routing around it**
  (`refusal-finetuning`). The projection on it falls from 5.0 to about 1.0 as refusal reaches 0.
- **Retrieved state injected at one mid layer carries nothing** (`retrieval-injection`, active).
  Closed book F1 0.01, passages in the prompt 0.46, injected at layer 12 0.00. Which layer, if any,
  carries them is the open question.
- **Faster attention kernels agree with eager; approximate ones do not** (`attention-kernels`).
  sdpa and flex_attention: KL 0.008 from eager; a sliding window of 8: KL 3.56.

Open, in the [roadmap](docs/ROADMAP.md): the layer sweep for retrieval inside the model, a caving
direction for sycophancy on a 1.5B to 3B model, and the instrument checks on full splits.

## A new question

```
just new-experiment my-question mechanisms
```

This writes `experiments/my-question/README.md` with the research-note template and a `run.py`
that logs to Inspect and MLflow, so the run appears in the app and Launch gets a form for its
options. Domains are listed in [the docs](apps/site/content/docs/domains.mdx).

## Install

```
pip install 'loupelab[server,interp]'
loupe serve
```

Open http://127.0.0.1:8000. Extras for training, SAEs and retrieval are in the
[install docs](apps/site/content/docs/install.mdx). The package is `loupelab`; the import and the
command are `loupe`. Built on nnsight, Inspect, TRL, PEFT, SAELens, circuit-tracer and MLflow
([how each runs](docs/ARCHITECTURE.md)).

## Develop

Needs [just](https://just.systems), [uv](https://docs.astral.sh/uv) and Node 22 with pnpm.

```
just bootstrap     # dependencies and git hooks
just check         # lint, types, layers, tests, UI and site builds
just serve         # API and UI on :8000
```

## License

[Apache 2.0](LICENSE)
