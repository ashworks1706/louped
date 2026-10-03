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
| Behavior & alignment | Sycophancy and honesty | `rational-updating-baseline` (Experiment 1A) |
| Efficiency & systems | | none yet |

Every domain is listed in [the docs](apps/site/content/docs/domains.mdx).

## A new question

Press New on the Experiments page (or `loupe new my-question --domain honesty`). It writes
`experiments/my-question/` with the research-note README and a `run.py` whose options become a
form on Launch and whose runs file under the experiment. What goes where is in
[Writing an experiment](apps/site/content/docs/experiments.mdx).

## From a coding agent

`loupe mcp` lets Claude Code, Cursor or any MCP client read runs and launch experiments
through the app's queue. Setup is in [the docs](apps/site/content/docs/agents.mdx).

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
