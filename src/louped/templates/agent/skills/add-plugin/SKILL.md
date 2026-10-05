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

   For each page:
   - Use plain HTML and JavaScript, or a built bundle. It calls `/api/...` as the app does.
   - Style it only with the app's variables: `var(--background)`, `var(--foreground)`,
     `var(--muted-foreground)`, `var(--border)`, `var(--font-geist-sans)`,
     `var(--font-geist-mono)` for numbers. Use no other colours.
   - Keep it to one question per page, with little text, as the rest of the app is.
5. Restart `louped serve` and open the plugin's sidebar entry, or its tab on a run or experiment.
   A load error shows on its page.
   Test the routes with FastAPI's `TestClient`.
6. Commit the plugin with the project. It runs only where launching is on: never with `--expose`
   or in a published dashboard.
