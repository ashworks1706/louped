<p align="center"><img src="docs/brand/wordmark.svg" alt="loupe" height="48"></p>
<p align="center">Look inside the model you're testing.</p>

<p align="center">
  <a href="docs/ARCHITECTURE.md">Architecture</a> •
  <a href="docs/ROADMAP.md">Roadmap</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

loupe makes an intervention a first-class object. A steered or ablated model is a drop-in policy:
an Inspect eval scores it, a paired test says whether it changed anything, a sweep maps where it
works and what it costs in coherence, a trainer can train against it, and the same UI shows what
changed inside the model, from the transcript down to the activation behind a number, and across
training checkpoints.

It builds on proven open-source tools and runs them inside one app:
[nnsight](https://nnsight.net) for interpretability, [Inspect](https://inspect.aisi.org.uk) for
evals and agents, [TRL](https://github.com/huggingface/trl) and
[pyreft](https://github.com/stanfordnlp/pyreft) for training, [SAELens](https://github.com/jbloomAus/SAELens)
for sparse autoencoders with feature dashboards computed locally,
[circuit-tracer](https://github.com/safety-research/circuit-tracer) for attribution graphs,
[Inspect View](https://inspect.aisi.org.uk/log-viewer.html) for transcripts and
[MLflow](https://mlflow.org) for tracking. Every one of them is launched, configured and read from
loupe's UI; the ones that pin older libraries run in environments of their own.

Everything runs on your machine with no API keys: open-weight models from the Hugging Face Hub or
a local path, results in files under `LOUPE_HOME`, and no step that calls a hosted model. A GPU
makes the big models practical; every pipeline also runs on CPU with a tiny model for checking.

> Status: v0.7. Interventions (steer, ablate, inject) with lens, attention, projection, patching
> and probes; Inspect evals under interventions with paired statistics, steering sweeps and
> condition grids over seeds; adapter banks with phase routing; masked diffusion models; RAG and
> retrieval inside the model; SFT, soft prompts, DPO and GRPO on TRL, teacher distillation, and
> interp across checkpoints; tool agents in Docker. See the [roadmap](docs/ROADMAP.md).

## Quick start

Needs [just](https://just.systems), [uv](https://docs.astral.sh/uv) and Node 22 with pnpm.

```
just bootstrap     # dependencies and git hooks
just check         # the gate: lint, types, layers, tests, UI build
just serve         # API on :8000, serving the built UI
just web           # UI dev server on :3000, against the API on :8000
```

## Install

```
pip install 'loupelab[server]'           # the UI over your runs
pip install 'loupelab[server,interp]'    # plus steering, ablation and the Playground
pip install 'loupelab[train]'            # plus loupe data and loupe train
pip install 'loupelab[rag]'              # plus retrieval and the classifier recipe
loupe serve --model Qwen/Qwen2.5-0.5B-Instruct
```

The package is `loupelab`; the import and the command are `loupe`.

## License

[Apache 2.0](LICENSE)
