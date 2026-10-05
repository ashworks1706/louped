---
name: change-ui
description: Change what louped's pages show (reorder, hide, retitle, add text or a card, add a tab, pick a preset, set the theme) through layouts, keeping the app louped's own. Use when the user asks to change a page, a card, a tab or the look, or points at a block in the app.
---

1. Find what the user means:
   - "this", "that card", "here": call `ui_selection`. Its `id` is `<region>/<block>[/<which>]`,
     with the page's url and its run or experiment. A reference the user pasted
     (`louped block run.overview/metrics ...`) says the same.
   - An id starting with `shell.` or ending in `.header` is louped's own frame, not a layout: say
     it stays as it is, and offer a block beside it instead.
2. Read the page with `ui_page` (with `experiment` for an experiment's page or its runs' pages).
   It gives each region's blocks and where they come from, the blocks each region can hold, and
   the presets.
3. Pick the smallest change that does it, in this order:
   - A preset (`set_preset`): `eval` opens runs on their items, `training` puts curves first,
     `focus` keeps only numbers, report, items and files.
   - Reorder, drop, retitle or resize blocks in one region (`set_layout`). `title` renames a
     block or tab; `about` is its ?, saying how to read it; `width` is `full`, `half` (two side
     by side) or `side` (a narrow column).
   - Add a built-in block: `metric` (`key`) for one number, `file` (`path`) for a file the run
     wrote, as a block or its own tab, `figure` (`index`), `text` (`text`, Markdown) for a note.
   - Only when nothing built in shows it, a `plugin` block (`plugin`, and `page` for a file in
     its `panel/`): follow `add-plugin`, and build the page from the kit (step 5).
4. Scope: a change for one experiment's pages goes in its layout (`experiment` set); one for every
   page goes in the project's. `set_layout` with `blocks` null removes a region from the file.
5. Keep it louped's own:
   - One question a page. Add a block only for what that page answers; prefer moving or
     retitling to adding.
   - Little text: a `text` block is one or two sentences, not a manual. A block's `about` says
     how to read it, in one sentence.
   - Numbers are `metric` cards or the kit's `stats`; never a sentence with a number in it.
   - A plugin page links `/kit/louped.css` and imports `/kit/louped.js`, and uses only their
     classes (`l-card`, `l-stats`, `l-table`, `l-button`, `l-muted`, `l-empty`) and helpers
     (`api`, `stats`, `table`, `h`, `empty`): no colours, fonts or shadows of its own, no other
     CSS framework.
   - The theme (`[theme]` in `louped.toml`) changes token values only: `radius`, and under
     `[theme.light]` and `[theme.dark]` the colours (`border`, `muted-foreground`, ...).
     `intervention` stays the one accent, for an active intervention only.
6. `set_layout` checks blocks before writing and the app shows the change at once. Read
   `errors` in its answer; a file with errors is not used. Tell the user what changed and where
   (`layout.json` or `experiments/<name>/layout.json`), and that the file is theirs to commit.
