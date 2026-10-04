<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# loupe web: design rules

The UI is the product: quiet, dense, keyboard-first.

- Components come from shadcn/ui, copied into `src/components/ui/`. Do not add another component
  library. A new primitive is a shadcn one, adapted, not designed from scratch.
- Colours are the tokens in `src/app/globals.css` only. Neutral greys, black and white.
  `intervention` is the one accent and means "an intervention is active"; `positive` and
  `negative` are for deltas. No new colours, no gradients, no shadows except on overlays.
- Type: Geist Sans for text, Geist Mono for numbers, ids and commands. Numbers right-aligned.
- Every page answers one question. Its header says which, in one line (`src/lib/nav.ts`).
- Every page has an empty state with what fills it: a link into the app (Launch, Load examples).
  A terminal command only where the app cannot act, such as starting the server or making an
  experiment folder (the app reads experiments, it does not write them).
- Launching opens the job's page; jobs are followed on Runs, never on Launch.
- Every figure has a ? beside its title saying how to read it: the view's `about`, set where the
  figure is made.
- Pages are filed by section in `NAV`: the workspace, or a research domain (Behavior, Efficiency),
  each domain a sidebar of its own. A new tool goes under the domain whose question it answers.
- A technical term gets its ? from `src/lib/glossary.ts` (`Term`, `MetricName`), so it reads the
  same everywhere.
- Every navigation is reachable from the ⌘K menu; new pages go in `NAV` and get a `G <key>` jump.
- No client state library. View state lives in the URL; server data comes from the API.
- The export is static (`output: "export"`): no server actions, no route handlers, no middleware.
- Done means `pnpm lint`, `pnpm typecheck`, `pnpm build` and `pnpm test:e2e` pass, and the
  screenshots in `test-results/` look right in dark, light and mobile.
