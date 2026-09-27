<p align="center"><b>loupe</b></p>
<p align="center">a research testbed for looking inside language models</p>

<p align="center">
  <a href="docs/ARCHITECTURE.md">Architecture</a> •
  <a href="docs/ROADMAP.md">Roadmap</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

loupe puts interpretability, evals, training and RL environments behind one model, one
intervention spec and one UI. A steered, ablated or patched model is a drop-in policy: the same
eval scores it, the same trainer can train against it, and the same UI shows what changed, down to
the transcript and the activation behind a number.

It is glue, not a framework. The work is done by [nnsight](https://nnsight.net),
[Inspect](https://inspect.aisi.org.uk), [TRL](https://github.com/huggingface/trl),
[verifiers](https://github.com/willccbb/verifiers), [vLLM](https://github.com/vllm-project/vllm) and
[MLflow](https://mlflow.org); loupe connects them and shows the results.

Everything runs on your machine with no API keys: open-weight models from the Hugging Face Hub or
a local path, results in files under `LOUPE_HOME`, and no step that calls a hosted model. A GPU
makes the big models practical; every pipeline also runs on CPU with a tiny model for checking.

> Status: v0.4, with v0.5 training underway. Interpretability (steering, ablation, lens,
> patching), Inspect evals under interventions, a Playground, and LoRA SFT from product traces.
> See the [roadmap](docs/ROADMAP.md).

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
loupe serve --model Qwen/Qwen2.5-0.5B-Instruct
```

The package is `loupelab`; the import and the command are `loupe`.

## License

[Apache 2.0](LICENSE)
