# Roadmap

loupe grows when an experiment needs it. This file holds two tracks: the **product**, what a
researcher installs, and the **research** that drives it and proves it works.

## What loupe is

A research workbench for language models that your coding agent drives. It has three parts:

| Part               | What it is                                                                     | Who changes it                                |
| ------------------ | ------------------------------------------------------------------------------ | --------------------------------------------- |
| The package        | `pip install loupelab`: the library, the `loupe` CLI, the API and the UI       | loupe's maintainers                           |
| A research project | a folder `loupe init` makes: your questions as experiments, under git          | the researcher and their agent                |
| The agent harness  | `loupe mcp`, the skills and an `AGENTS.md`, given to the agent you already use | loupe ships it; any MCP-capable agent uses it |

The person reads, steers and judges in the UI; the agent writes experiments, launches them and
reads results through the harness; loupe keeps both honest (fixed cohorts, paired intervals,
RunMeta on every result).

### Decisions

- **Bring your own agent; no built-in one.** Claude Code, Codex, Cursor and Gemini CLI already
  write and run code well, and research tools are converging on exposing themselves to them
  (MCP servers from MLflow, W&B, Hugging Face; Jupyter AI over ACP; marimo's agent skill) rather
  than shipping their own. A built-in agent would also need a hosted model, which the local rule
  forbids. loupe's job is the harness: tools, conventions, guardrails.
- **A project is a folder of code; state is a folder beside it.** As with Inspect (`logs/`),
  MLflow (`mlruns/`), dbt (`target/`) and DVC (`.dvc/cache`): what you write is committed, what
  loupe writes is gitignored.

  ```
  my-research/              loupe init; a git repo
    loupe.toml              the project: its domains, defaults; marks the root
    experiments/<question>/ README.md (question, hypotheses, stop if), run.py, task.py   committed
    AGENTS.md               how an agent works here                                     committed
    .mcp.json, .claude/     loupe mcp and the skills, for the agent                     committed
    .loupe/                 runs, logs, jobs, vendored harnesses, caches                ignored
  ~/.cache/huggingface      models, shared across projects
  ```

  `experiments/` stays out of `.loupe/` because it is the research itself: written by hand or by
  an agent, reviewed, versioned. `.loupe/` can be deleted and rebuilt from it.

- **The product repository is not a research project.** loupe's repo holds the package, tests,
  the UI and `src/loupe/templates/` (what `loupe init` copies); a research question lives in its
  own project.
  `rational-updating-baseline` now lives in its own project, `honesty-research`.
- **A way in without adopting loupe.** `loupe view <folder>` opens what a researcher already
  has (Inspect logs, an MLflow store, a folder of per-condition JSONL) in the run page, with no
  project.

## Product

### 1. Installable: from pip to a first result in five minutes

- [x] The wheel carries the UI: the static export built at release into `loupe/web`, served by
      `loupe serve` by default (today it looks for `apps/web/out` in the working directory).
- [x] `loupe init [dir]`: `loupe.toml`, `experiments/`, `AGENTS.md`, `.mcp.json`, the skills,
      a `.gitignore` with `.loupe/`, and one example experiment that runs on CPU in minutes and
      ends on the Items view (`--example none` to skip it).
- [x] The project root is found by walking up to `loupe.toml`, as git finds `.git`, so commands
      work from any subfolder; `LOUPE_HOME` and `LOUPE_EXPERIMENTS` still override.
- [x] Domains come from `loupe.toml`, defaulting to today's list, instead of a list in
      `src/loupe/stores/experiments.py`: another lab's questions are not ours.
- [x] CI installs the built wheel in an empty folder and runs `loupe init`, the example, and
      `loupe serve`, then checks the Items view.
- [ ] Published to PyPI on a `v*` tag (trusted publishing is configured once, by hand, on PyPI).
- [ ] An exported Sol job installs the released version when the project is not a loupe checkout
      (the bundle does so and carries the project's `loupe.toml`; untried until the first release).

### 2. A way in: `loupe view`

- [x] `loupe view <path>`: serve the UI read-only over a folder of Inspect logs, an MLflow store or
      JSONL files; no project, no write routes.
- [x] The run page's Items view works on any folder of per-condition JSONL sharing an item id
      (done: Items, Artifacts previews, Provenance on the run page).

- [x] One file of records with a condition or arm column (a JSON array or JSONL, as an engine's
      own benchmark writes) lines up on its Artifacts page by that column.
- [x] `loupe endpoint-bench <url>...`: time to first token, latency and throughput of
      OpenAI-compatible servers (llama-server, vLLM, a Rust engine) by concurrency, every request
      recorded so servers line up item by item; for models loupe does not load (GGUF, own engines).
- [x] Recipes in the docs for models served elsewhere, engines with their own harness, retrieval,
      adapters and small models.

### 3. The agent harness

- [x] `loupe mcp` gains the steps an agent now does by shell: `new_experiment`, `export_job` and
      `import_result`; reads stay the default, writes stay off with `--expose`.
- [x] The skills (`new-experiment`, `check`, reading a run, reproducing a paper) ship in the
      package, are copied by `loupe init`, and are offered as a Claude Code plugin; plain skill
      folders serve Codex and Cursor. Descriptions stay short: they cost context on every turn.
- [x] `AGENTS.md` for a project: the method (question, baseline, test, stop if), fixed cohorts,
      paired intervals, RunMeta, Sol as the place for real runs.
- [ ] A recorded session: an agent asked to test one question writes, launches and reads it, and
      the run page fills in.

### 4. Separate the product from the research

- [x] `experiments/rational-updating-baseline` moves to its own project made with `loupe init`;
      this repo keeps the templates and tests (done: `~/projects/honesty-research`, its Sol run
      imported there; it needs a GitHub remote of its own). The research project is the first real user of
      `loupe init`, so it lands with item 1.
- [x] `ARCHITECTURE.md` and the docs site describe the package and a project separately.

### 5. Show it

- [ ] Three researchers outside this repo (ARC Lab first) run one question each; what stops them
      becomes the next items here.
- [ ] A read-only demo of real runs (the Docker image already serves results) and the docs site,
      deployed. The repository is private, so GitHub Pages needs a paid plan or a public
      repository; the site also builds as a server app today, not a static export.
- [ ] The case study: Experiment 1A reproduced and one mitigation tested, item by item, written up
      with the tool's part in it.
- [ ] Then a public launch and, if the case study holds, a demo or workshop paper.

Not planned: a built-in agent, a hosted service, accounts or auth, a tracking server of our own.

## Research

Each item is a research outcome or the check that makes one trustworthy; the experiment it lives
in is named.

### Acceptance

Behavior and alignment:

- [ ] Experiment 1A: the rational-updating harness reproduces the published unmitigated
      Llama-3.1-8B-Instruct baseline on TruthfulQA, rates and denominators within the README's
      margin, with ten examples read by hand (`rational-updating-baseline`). The 20-item run on
      Sol works end to end (2026-10-04); the full split is next.
- [ ] Experiment 1B: one mitigation on the fixed 1A cohort, scored on resisting unsupported
      pressure and on keeping evidence-based correction, preferably on a dataset where the model
      writes its answer.
- [ ] One mechanism result on a real model, read entirely in the UI.

Efficiency and systems:

- [ ] None yet; questions come later.

Instrument checks:

- [ ] An inspect_evals score within noise of the reported number on the full split.

### Next

- A human-calibration study in `honesty`: an agent adapting to a simulated person over repeated
  turns, with no personal state, ordinary preference memory, and preferences kept apart from
  factual claims, scored on useful adaptation and on correctness under pressure.
- More checks: IFEval (needs its optional package), a memory benchmark across conversations
  (LongMemEval or LoCoMo), citation accuracy (ALCE), and a HotpotQA grounding task with its
  paragraphs retrieved or injected.
- RunMeta with the model's revision, a dataset fingerprint and the chat template's hash.
