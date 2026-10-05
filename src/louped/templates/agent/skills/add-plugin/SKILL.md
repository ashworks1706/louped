---
name: add-plugin
description: Add a page, a tab on every run or experiment, API routes, a command or agent tools to louped from this project's plugins/ folder. Use when the user wants something in the app that views and existing pages do not give.
---

1. Check that a plugin is needed:
   - A chart or table is a view (`louped.analysis.views`), and `views.vega` draws any Vega-Lite
     chart.
   - A report is Markdown the run logs.
   - Write a plugin only for a page, a tab, routes, a command or tools.
2. Make `plugins/<name>/plugin.toml`, with the name in lowercase letters, digits and `-`:
   `title`, `section` (`workspace`, `behavior` or `efficiency`) and a one-line `description`.
3. Put code in `plugins/<name>/plugin.py`, and only the parts the feature needs:
   - `router`, a FastAPI `APIRouter`, served at `/api/x/<name>`. It reads louped's stores (the
     runs' files, MLflow, Inspect logs) instead of keeping a copy. It writes only files the user
     owns.
   - `main(argv)`, run as `louped <name> ...`.
   - `tools(mcp, api)`, which adds MCP tools that call the plugin's routes through `api`, an
     httpx client of the server.
4. Put pages in `plugins/<name>/panel/`, only the ones the feature needs:
   - `index.html`: a page of its own, at the plugin's sidebar entry.
   - `run.html`: a tab on every run's page, opened with `?run=<run id>`. Use it to show a run
     your way where the user already looks.
   - `experiment.html`: a tab on every experiment's page, opened with `?experiment=<name>`.

   - Any other `<page>.html`: a block a layout places anywhere (`change-ui`), opened with the
     run or experiment of the page it is on.

   For each page:
   - Build it from louped's kit, so it looks like the app: `<link rel="stylesheet"
     href="/kit/louped.css">` and `import { api, run, experiment, stats, table, h, empty } from
     "/kit/louped.js"` in a module script. `api(path)` reads `/api<path>`; `stats` and `table`
     draw the app's metric cards and tables. As a block, the kit fits its frame to the page.
   - Use only the kit's classes (`l-card`, `l-stats`, `l-table`, `l-button`, `l-input`,
     `l-badge`, `l-muted`, `l-mono`, `l-empty`) and the app's variables (`var(--foreground)`,
     `var(--border)`, ...). No colours, fonts, shadows or CSS frameworks of its own.
   - Keep it to one question per page, with little text, as the rest of the app is.
5. Restart `louped serve` and open the plugin's sidebar entry, or its tab on a run or experiment.
   A load error shows on its page.
   Test the routes with FastAPI's `TestClient`.
6. Commit the plugin with the project. It runs only where launching is on: never with `--expose`
   or in a published dashboard.
