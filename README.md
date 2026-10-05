<p align="center"><img src="https://louped.vercel.app/wordmark.svg" alt="louped" height="48"></p>
<p align="center">A local workbench for research on LLM behavior and efficiency.</p>

<p align="center">
  <a href="https://louped.vercel.app">Website</a> •
  <a href="https://louped.vercel.app/docs">Docs</a>
</p>

Keep your research questions about language models in a project. Each question is an experiment
with a README (the question and the test) and a script that runs it. Your coding agent writes and
runs them; you read the results item by item in louped's app. Everything runs on your machine or
your cluster, with open-weight models.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://louped.vercel.app/demo/items-dark.png">
  <img alt="Sixteen questions under three conditions: what pushback and evidence did to each answer" src="https://louped.vercel.app/demo/items-light.png">
</picture>

## Start

```sh
pip install 'louped[server,tracking,interp,agent]'
louped init my-research && cd my-research
louped serve
```

Open http://127.0.0.1:8000 and launch the example experiment.

## How it works

1. **Make a project** with `louped init`. It also connects your coding agent.
2. **Ask a question.** Your agent (Claude Code, Codex, Cursor) writes the experiment.
3. **Run it** on your machine, or send it to a Slurm cluster; with a remote set, the job pushes
   its results and `louped pull` brings them in.
4. **Read the results**: every item under every condition, what changed, and out of how many.
   Edit a run's write-up beside its rendering; delete what you no longer need to the trash.
5. **Share and shape it.** Push runs for others to pull, or publish a read-only dashboard. Point
   at any part of a page and ask your agent to change it: layouts, notes, cards of your own.

Already have results? `louped view <folder>` opens them read-only.

See the [docs](https://louped.vercel.app/docs) for writing experiments, changing models, using
your agent and running on a cluster.

## Develop

You need [just](https://just.systems), [uv](https://docs.astral.sh/uv) and Node 22 with pnpm.

```sh
just bootstrap     # install everything and the git hooks
just check         # lint, types, tests, and the app and site builds
just serve         # the app on :8000
```

## License

[Apache 2.0](LICENSE)
