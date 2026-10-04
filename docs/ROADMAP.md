# Roadmap

louped grows when an experiment needs it. This file is the product: what a researcher installs.
Research questions live in research projects, each with its own roadmap; the maintainer's
(`arc-lab`: sycophancy and misleading outputs) is the first user and sets what is next
here, but its experiments are not louped's.

## What louped is

A research workbench for language models that your coding agent drives. It has three parts:

| Part               | What it is                                                                      | Who changes it                                 |
| ------------------ | ------------------------------------------------------------------------------- | ---------------------------------------------- |
| The package        | `pip install louped`: the library, the `louped` CLI, the API and the UI         | louped's maintainers                           |
| A research project | a folder `louped init` makes: your questions as experiments, under git          | the researcher and their agent                 |
| The agent harness  | `louped mcp`, the skills and an `AGENTS.md`, given to the agent you already use | louped ships it; any MCP-capable agent uses it |

The person reads, steers and judges in the UI; the agent writes experiments, launches them and
reads results through the harness; louped keeps both honest (fixed cohorts, paired intervals,
RunMeta on every result).

### Decisions

- **Bring your own agent; no built-in one.** Claude Code, Codex, Cursor and Gemini CLI already
  write and run code well, and research tools are converging on exposing themselves to them
  (MCP servers from MLflow, W&B, Hugging Face; Jupyter AI over ACP; marimo's agent skill) rather
  than shipping their own. A built-in agent would also need a hosted model, which the local rule
  forbids. louped's job is the harness: tools, conventions, guardrails.
- **A project is a folder of code; state is a folder beside it.** As with Inspect (`logs/`),
  MLflow (`mlruns/`), dbt (`target/`) and DVC (`.dvc/cache`): what you write is committed, what
  louped writes is gitignored.

  ```
  my-research/              louped init; a git repo
    louped.toml              the project: its domains, defaults; marks the root
    experiments/<question>/ README.md (question, hypotheses, stop if), run.py, task.py   committed
    AGENTS.md               how an agent works here                                     committed
    .mcp.json, .claude/     louped mcp and the skills, for the agent                     committed
    .louped/                 runs, logs, jobs, vendored harnesses, caches                ignored
  ~/.cache/huggingface      models, shared across projects
  ```

  `experiments/` stays out of `.louped/` because it is the research itself: written by hand or by
  an agent, reviewed, versioned. `.louped/` can be deleted and rebuilt from it.

- **The product repository is not a research project.** louped's repo holds the package, tests,
  the UI and `src/louped/templates/` (what `louped init` copies); a research question lives in its
  own project.
  The maintainer's research lives in its own project, `arc-lab`.
- **A way in without adopting louped.** `louped view <folder>` opens what a researcher already
  has (Inspect logs, an MLflow store, a folder of per-condition JSONL) in the run page, with no
  project.

## Product

### 1. Installable: from pip to a first result in five minutes

- [x] The wheel carries the UI: the static export built at release into `louped/web`, served by
      `louped serve` by default (today it looks for `apps/web/out` in the working directory).
- [x] `louped init [dir]`: `louped.toml`, `experiments/`, `AGENTS.md`, `.mcp.json`, the skills,
      a `.gitignore` with `.louped/`, and one example experiment that runs on CPU in minutes and
      ends on the Items view (`--example none` to skip it).
- [x] The project root is found by walking up to `louped.toml`, as git finds `.git`, so commands
      work from any subfolder; `LOUPED_HOME` and `LOUPED_EXPERIMENTS` still override.
- [x] Domains come from `louped.toml`, defaulting to today's list, instead of a list in
      `src/louped/stores/experiments.py`: another lab's questions are not ours.
- [x] CI installs the built wheel in an empty folder and runs `louped init`, the example, and
      `louped serve`, then checks the Items view.
- [ ] Published to PyPI on a `v*` tag (trusted publishing is configured once, by hand, on PyPI).
- [ ] An exported Sol job installs the released version when the project is not a louped checkout
      (the bundle does so and carries the project's `louped.toml`; untried until the first release).

### 2. A way in: `louped view`

- [x] `louped view <path>`: serve the UI read-only over a folder of Inspect logs, an MLflow store or
      JSONL files; no project, no write routes.
- [x] The run page's Items view works on any folder of per-condition JSONL sharing an item id
      (done: Items, Artifacts previews, Provenance on the run page).

- [x] One file of records with a condition or arm column (a JSON array or JSONL, as an engine's
      own benchmark writes) lines up on its Artifacts page by that column.
- [x] `louped endpoint-bench <url>...`: time to first token, latency and throughput of
      OpenAI-compatible servers (llama-server, vLLM, a Rust engine) by concurrency, every request
      recorded so servers line up item by item; for models louped does not load (GGUF, own engines).
- [x] Recipes in the docs for models served elsewhere, engines with their own harness, retrieval,
      adapters and small models.
- [x] The machine on every run: GPU power, utilisation and memory, CPU and RAM sampled while it is
      open, with the GPU energy, under Hardware on its Overview; joules per token in
      `endpoint-bench` for a server on this machine.
- [x] `remote_code`: a Hub model with modeling code of its own (an engine's trained layers) loads,
      opt-in, so louped's hooks reach its new layers.
- [x] Agent traces as timelines: records with a time and a kind on every event open per request,
      with offsets, durations and every field; a folder of trace files reads as one.
- [x] `inject` at an engine's hook points: every token, the prompt only, or chunk boundaries of
      the reply, so a retrieval-during-generation design is studied here and checked against the
      engine's endpoint.

### 3. The agent harness

- [x] `louped mcp` gains the steps an agent now does by shell: `new_experiment`, `export_job` and
      `import_result`; reads stay the default, writes stay off with `--expose`.
- [x] The skills (`new-experiment`, `check`, reading a run, reproducing a paper) ship in the
      package, are copied by `louped init`, and are offered as a Claude Code plugin; plain skill
      folders serve Codex and Cursor. Descriptions stay short: they cost context on every turn.
- [x] `AGENTS.md` for a project: the method (question, baseline, test, stop if), fixed cohorts,
      paired intervals, RunMeta, Sol as the place for real runs.
- [ ] A recorded session: an agent asked to test one question writes, launches and reads it, and
      the run page fills in.

### 4. Separate the product from the research

- [x] The maintainer's experiments move to their own project made with `louped init`;
      this repo keeps the templates and tests (done: `~/projects/arc-lab`, its Sol run
      imported there; it needs a GitHub remote of its own). The research project is the first real user of
      `louped init`, so it lands with item 1.
- [x] `ARCHITECTURE.md` and the docs site describe the package and a project separately.

### 5. Show it

- [ ] Three researchers outside this repo (ARC Lab first) run one question each; what stops them
      becomes the next items here.
- [ ] A read-only demo of real runs (the Docker image already serves results) and the docs site,
      deployed. The repository is private, so GitHub Pages needs a paid plan or a public
      repository; the site also builds as a server app today, not a static export.
- [ ] The case study: a real result made with louped (the first from `arc-lab`), written
      up item by item with the tool's part in it.
- [ ] Then a public launch and, if the case study holds, a demo or workshop paper.

Not planned: a built-in agent, a hosted service, accounts or auth, a tracking server of our own.

## Trust

What makes louped's own numbers trustworthy, whatever the question.

- [ ] An inspect_evals score within noise of the reported number on the full split.
- [ ] RunMeta with the model's revision, a dataset fingerprint and the chat template's hash.
- More checks: IFEval (needs its optional package), a memory benchmark across conversations
  (LongMemEval or LoCoMo), citation accuracy (ALCE), and a HotpotQA grounding task with its
  paragraphs retrieved or injected.
