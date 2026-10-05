# Roadmap

### 1. Release

- [x] louped on PyPI: `pip install louped` works for anyone (0.3.0).
- [ ] The repository made public, after removing private project names from its history.
- [ ] The docs site on a public address, with a read-only demo of real runs beside it
      (`louped publish` writes the demo).
- [x] Runs shared through a remote (`louped push`/`pull`); cluster jobs push their own results.

### 2. The agent harness

- [ ] A recorded session: an agent asked to test one question writes, launches and reads it, and
      the run page fills in.
- [ ] `louped init` adds its part to an existing `AGENTS.md` and `.mcp.json` instead of leaving
      them as they are.
- [ ] Skills packaged for Codex and Cursor too, not only Claude Code.

### 3. Reading results

- [ ] Compare two runs item by item, not only conditions within one run.
- [ ] Notes on items: mark whether the scoring was right and whether a change was reasonable, saved
      with the run.
- [ ] Follow a cluster job from the app while it runs, not only import it at the end.

### 4. Projects

- [ ] The experiments folder's location set in `louped.toml`, for repositories that already use
      `experiments/` for something else.
- [ ] A project records the louped version it uses, and louped warns when it differs.
- [ ] macOS (Apple GPUs) and Windows checked. Only Linux is tested today.

### 5. Show it

- [ ] Three researchers outside this repo run one question each; what stops them becomes the
      next items here.
- [ ] The case study: a real research result made with louped, written up item by item with the
      tool's part in it.
- [ ] Then a public launch and, if the case study holds, a demo or workshop paper.

Not planned: a built-in agent, a hosted service, accounts or auth, a tracking server of our own.
