# Introduction

What louped is and how it is used.

louped is a local workbench for research on language models: how they behave, and what they cost
to run.

You keep your research questions in a project. Each question is an experiment. It has:

- a README that states the question and how you will test it
- a script that runs the test

Your coding agent writes and runs the experiments. You read the results in louped's app.

## How it is used

1. **Make a project.** `louped init my-research` sets up the folders and connects your coding
   agent.
2. **Ask a question.** Tell your agent (Claude Code, Codex, Cursor) what to test. It writes the
   experiment.
3. **Run it.** Small runs go on your machine. Large ones go to a Slurm cluster, which pushes the
   results to your remote. **Pull** brings them into your app.
4. **Read the results.** The run page shows every item under every condition, what changed, and
   out of how many. Edit any text file a run wrote beside its rendering.
5. **Share and shape it.** Push runs for others to pull, or publish a read-only dashboard.
   Shift+click rows, cards or fields to ask your agent about them, or to have it change them. The
   agent points back at what it means.

Everything runs on your hardware with open-weight models. No API key is needed.


## All pages

- [Get started](quickstart.md): Install louped, make a project and run the example.

**Guides**

- [Write an experiment](experiments.md): What goes in an experiment's folder, and how its results show in the app.
- [Group experiments in projects](projects.md): A project holds the experiments that serve one goal, with its README, links and runs.
- [Sources](sources.md): The papers, docs, slides and notebooks your claims rest on, kept with the project.
- [Datasets and benchmarks](datasets.md): The data your project uses, and leaderboards of evals and speed runs.
- [Reports](reports.md): Write-ups, decks, documents and figures, each number traced to the run it came from.
- [Use your coding agent](agents.md): Let Claude Code, Codex or Cursor write, run and read your experiments.
- [Change a model](changes.md): Steer, ablate, inject and swap adapters, and compare the result against a baseline.
- [Share and run elsewhere](remote.md): Keep runs in a remote everyone can pull from, send jobs to a cluster or Colab, and publish a read-only dashboard.
- [Customize the app](customize.md): Pick any part of a page for your agent, have it change any part, and let it point back, in louped's own look.
- [Plugins](plugins.md): Add pages, tabs, blocks, routes, a command or agent tools to louped from your own project.
- [Recipes](recipes.md): How to run common kinds of experiments.

**Reference**

- [Supported models](models.md): Which model families work with which parts of louped.
- [CLI](cli.md): Every louped command.
- [Share results](self-host.md): Serve the app read-only with Docker.
