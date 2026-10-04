<p align="center"><img src="docs/brand/wordmark.svg" alt="louped" height="48"></p>
<p align="center">A local testbed for research on LLM behavior and efficiency.</p>

<p align="center">
  <a href="apps/site/content/docs/domains.mdx">Domains</a> •
  <a href="docs/ARCHITECTURE.md">Architecture</a> •
  <a href="docs/ROADMAP.md">Roadmap</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

louped is where research questions about language models get answered. It studies two things:

- **Behavior and alignment**: what models do, and why.
- **Efficiency and systems**: what it costs to run them.

Each question is an experiment: a folder in your project's `experiments/` with a stated question,
the observation behind it, competing hypotheses, a baseline, a controlled test, a stop condition
and a result. The app shows which questions are active, launches their runs and reads every result
back, item by item. Runs stay on your machine or your cluster, on open-weight models, with no
hosted model and no API key. Your coding agent does the plumbing through louped's MCP server.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="apps/site/public/demo/items-dark.png">
  <img alt="Sixteen questions under three conditions in louped: what pushback and evidence did to each answer" src="apps/site/public/demo/items-light.png">
</picture>

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

## Start

```
pip install 'louped[server,tracking,interp,agent]'
louped init my-research && cd my-research
louped serve
```

`louped init` makes a research project: `louped.toml` (the project's root and its domains),
`experiments/` with an example that runs on a CPU, `AGENTS.md`, and `.mcp.json` with skills for
your coding agent. What you write under `experiments/` is committed; what louped writes goes to
`.louped/`, gitignored. Open http://127.0.0.1:8000, Launch the example, and read it item by item on
its run page.

Already have results? `louped view <folder>` opens Inspect logs, an MLflow store or any folder of
JSONL, Markdown and CSV in the app, read-only, without a project.

## With your coding agent

louped has no agent of its own: it is the harness for the one you use. In a project, Claude Code,
Codex or Cursor read `AGENTS.md`, and `louped mcp` (in `.mcp.json`) lets them start a question,
launch it through the app's queue, export it to a cluster and read the results. Claude Code users
can also add louped as a plugin: `/plugin marketplace add ashworks1706/louped`, then
`/plugin install louped@louped`. Setup is in [the docs](apps/site/content/docs/agents.mdx).

## A new question

`louped new my-question --domain honesty` (or the agent's `new_experiment`) writes
`experiments/my-question/` with the research-note README and a `run.py` whose options become a
form on Launch and whose runs file under the experiment. What goes where is in
[Writing an experiment](apps/site/content/docs/experiments.mdx). Real runs on large models go to
Sol, a Slurm cluster or a VM ([Run elsewhere](apps/site/content/docs/remote.mdx)).

Extras for training, SAEs and retrieval are in the [install docs](apps/site/content/docs/install.mdx).
The package is `louped`; the import and the command are `louped`. Built on nnsight, Inspect,
TRL, PEFT, SAELens, circuit-tracer and MLflow ([how each runs](docs/ARCHITECTURE.md)).

## Develop

Needs [just](https://just.systems), [uv](https://docs.astral.sh/uv) and Node 22 with pnpm.

```
just bootstrap     # dependencies and git hooks
just check         # lint, types, layers, tests, UI and site builds
just serve         # API and UI on :8000
```

## License

[Apache 2.0](LICENSE)
