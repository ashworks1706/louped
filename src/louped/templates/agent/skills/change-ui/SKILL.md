---
name: change-ui
description: Change what louped's pages show (reorder, hide, rename or explain any card, row, field, column or control; add text or a card; add a tab; pick a preset; set the theme), and show the user parts of the app with a note. Use when the user asks to change a page or the look, refers to parts they picked in the app, or when an answer is clearer pointed at on screen.
---

1. Find what the user means:
   - "this", "these", "that card", "here": call `ui_selection`. It lists the parts the user
     Shift+clicked, in order, each with its address (`items/row/28`, `items/stat/pressure`,
     `item/field/evidence/second_turn`, `run.overview/metric/accuracy`), its page, run or
     experiment, its text and its `data`: an item's record under every condition, a condition's
     rate and flips, a field's value and meaning. Answer from that data first; it is what they see.
     A reference the user pasted (`louped part items/row/28 ...`) says the same.
2. Read the page with `ui_page` (with `experiment` for an experiment's page or its runs' pages).
   It gives each region's blocks and where they come from, the blocks each region can hold, the
   presets, the part rules in force (`parts`) and every kind of part by address with the rules it
   takes.
3. Pick the smallest change that does it, in this order:
   - A part (`set_part`): `hidden`, `label`, `about` (its ?), `note` (Markdown under it), `order`
     (among its siblings) and, for a control, `default` (its value when the URL sets none).
     `*` stands for any one name: `item/field/*/abstain` hides abstain in every section,
     `items/column/claim` hides one column. Names in addresses are URL-encoded.
   - A preset (`set_preset`): `eval` opens runs on their items, `training` puts curves first,
     `focus` keeps only numbers, report, items and files.
   - Reorder, drop, retitle or resize blocks in one region (`set_layout`). `title` renames a
     block or tab; `about` is its ?; `width` is `full`, `half` (two side by side) or `side`.
   - Add a built-in block: `metric` (`key`), `file` (`path`), as a block or its own tab,
     `figure` (`index`), `text` (`text`, Markdown) for a note.
   - Only when nothing built in shows it, a `plugin` block (`plugin`, and `page` for a file in
     its `panel/`): follow `add-plugin`, and build the page from the kit (step 5).
4. Scope: a change for one experiment's pages goes in its layout (`experiment` set); one for every
   page goes in the project's. A rule or region set to null is removed from the file.
5. Keep it louped's own:
   - One question a page. Prefer hiding, ordering and renaming to adding.
   - Little text: a note or `text` block is one or two sentences, not a manual. An `about` says
     how to read the part, in one sentence.
   - Never hide a denominator or an interval to make a difference look cleaner: a rate keeps its
     k/n and interval, a condition its flips.
   - Numbers are `metric` cards or the kit's `stats`; never a sentence with a number in it.
   - A plugin page links `/kit/louped.css` and imports `/kit/louped.js`, and uses only their
     classes (`l-card`, `l-stats`, `l-table`, `l-button`, `l-muted`, `l-empty`) and helpers
     (`api`, `stats`, `table`, `h`, `empty`): no colours, fonts or shadows of its own.
   - The theme (`[theme]` in `louped.toml`) changes token values only: `radius`, and under
     `[theme.light]` and `[theme.dark]` the colours. `intervention` stays the one accent.
6. `set_part`, `set_layout` and `set_preset` check before writing and the app shows the change at
   once. Read `errors` in the answer; a file with errors is not used. Tell the user what changed
   and where (`layout.json` or `experiments/<name>/layout.json`), and that the file is theirs to
   commit.
7. Show, don't describe: `ui_show` opens a page (`url`), scrolls to parts by address and points
   at them (`highlight`, `spotlight` to dim the rest, or `pointer`), with a one- or two-sentence
   note beside the first. Use it to put the evidence for an answer on screen, such as the item
   that flipped. It returns which parts were not on the page; open the page that has them
   (an item's panel is `&item=<id>` on the Items tab) and show again rather than guessing.
   One cue at a time: a newer one supersedes one the app is still looking for (status
   `superseded`).
