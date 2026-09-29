<p align="center"><img src="docs/brand/wordmark.svg" alt="loupe" height="48"></p>
<p align="center">Change a model, prove what changed, and see why.</p>

<p align="center">
  <a href="docs/ARCHITECTURE.md">Architecture</a> •
  <a href="docs/ROADMAP.md">Roadmap</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

loupe is a local app for research on language model behaviour. You change a model: steer or
ablate a direction, fine-tune it, rewrite its prompt, add an adapter. You prove what changed: the
same evals run on both versions, sample by sample, with paired intervals and a verdict on what
moved and what held. And you see why: logit lens, patching, probes, SAE features and circuits on
the same model under the same change. Every step is launched and read from one UI.

A change is one spec that runs the same way in an eval, a training run, the Playground and an
analysis. Your question is a short script in `experiments/`; loupe supplies the rest, built on
nnsight, Inspect, TRL and MLflow ([how each tool runs](docs/ARCHITECTURE.md)).

Everything runs on your machine: open-weight models from the Hugging Face Hub or a path, results
in files under `LOUPE_HOME`, no hosted model and no API key.

## Install

```
pip install 'loupelab[server,interp]'
loupe serve
```

Open http://127.0.0.1:8000 and start from Launch. Extras for training, SAEs and retrieval are in
the [install docs](apps/site/content/docs/install.mdx). The package is `loupelab`; the import and
the command are `loupe`.

## Develop

Needs [just](https://just.systems), [uv](https://docs.astral.sh/uv) and Node 22 with pnpm.

```
just bootstrap     # dependencies and git hooks
just check         # lint, types, layers, tests, UI build
just serve         # API and UI on :8000
```

## License

[Apache 2.0](LICENSE)
