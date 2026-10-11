<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# louped web: design rules

The UI is the product: quiet, dense, keyboard-first.

- Components come from shadcn/ui, copied into `src/components/ui/`. Do not add another component
  library. A new primitive is a shadcn one, adapted, not designed from scratch.
- Colours are the tokens in `src/app/globals.css` only. Neutral greys, black and white.
  `intervention` is the one accent and means "an intervention is active"; `positive` and
  `negative` are for deltas. No new colours, no gradients, no shadows except on overlays.
- Type: Geist Sans for text, Geist Mono for numbers, ids and commands. Numbers right-aligned.
- Every page answers one question. Its header says which, in one line (`src/lib/nav.ts`).
- Every page has an empty state with what fills it: a link into the app (Launch, Load examples).
  A terminal command only where the app cannot act, such as starting the server, or on a
  server that does not launch. The app creates a project folder and an experiment folder (New
  project, New experiment: a README from its template and, for an experiment, a run.py). Past
  that it edits only a README, a project's front matter, an experiment's `project:` line and a
  run's text files, with the text beside its rendering, and deletes only to the trash after one
  confirm; never when shared. Layouts are the agent's to edit, not the app's.
- Launching opens the job's page; jobs are followed on Runs, never on Launch.
- Every figure has a ? beside its title saying how to read it: the view's `about`, set where the
  figure is made.
- Pages are filed by section in `NAV`: the workspace, or a research domain (Behavior, Efficiency),
  each domain a sidebar of its own. A new tool goes under the domain whose question it answers.
- A technical term gets its ? from `src/lib/glossary.ts` (`Term`, `MetricName`), so it reads the
  same everywhere.
- Every navigation is reachable from the ⌘K menu; new pages go in `NAV` and get a `G <key>` jump.
- Home, a run's page and an experiment's page draw their regions from the layout
  (`useLayout`, `RegionGrid`; `src/louped/server/ui.py` holds the catalog). A new piece of those
  pages is a block: add it to `CATALOG` and `DEFAULT` there and to the region's renderer here, so
  agents can move it.
- Every part a person can see or use (a card, a row, a cell, a field, a column, a control, a
  heading) has an address: `part(partId("<area>/<kind>", ...names))` from `@/components/parts`,
  its kind listed in `KINDS` in `src/louped/server/parts.py`. That is what Shift+click picks and
  what `ui_show` points at. A part that takes rules reads them with `useRules()` and `arrange()`
  (hidden, label, about, note, order, default), and registers its data with `PartData` so a pick
  carries what it stands for. `e2e/parts.spec.ts` fails on anything without an address.
- Plugin pages draw with the kit (`/kit/louped.css`, `/kit/louped.js`); when the app gains a
  look the kit lacks, add it to the kit too.
- No client state library. View state lives in the URL; server data comes from the API.
- The export is static (`output: "export"`): no server actions, no route handlers, no middleware.
- Done means `pnpm lint`, `pnpm typecheck`, `pnpm build` and `pnpm test:e2e` pass, and the
  screenshots in `test-results/` look right in dark, light and mobile.
