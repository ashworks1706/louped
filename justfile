# loupe. `just` lists every recipe.

set dotenv-load := false

web := "apps/web"

default:
    @just --list

# first run: Python and UI dependencies, git hooks
bootstrap: setup
    uv run pre-commit install --hook-type pre-commit --hook-type pre-push

# install everything, locked
setup:
    uv sync --locked --all-extras
    cd {{web}} && pnpm install --frozen-lockfile

# the gate: CI and the hooks run exactly this
check: check-python check-web

# format, lint, types, layers, tests
check-python:
    uv run ruff format --check .
    uv run ruff check .
    uv run pyright
    uv run lint-imports
    uv run pytest -q

# format, lint, types, static build
check-web:
    cd {{web}} && pnpm format:check && pnpm lint && pnpm typecheck && pnpm build

# browser tests against the built UI (run check-web first)
test-e2e:
    cd {{web}} && pnpm test:e2e

# format everything in place
fmt:
    uv run ruff format .
    uv run ruff check --fix .
    cd {{web}} && pnpm format

# the API on :8000, serving the built UI when there is one
serve *args:
    uv run loupe serve {{args}}

# the UI dev server on :3000, against the API on :8000
web:
    cd {{web}} && pnpm dev

# build the UI's static export into apps/web/out
web-build:
    cd {{web}} && pnpm build

# re-resolve uv.lock after changing pyproject.toml
lock:
    uv lock

# scaffold experiments/<name>/ with its README and run.py
new-experiment name:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="experiments/{{name}}"
    [ -e "$dir" ] && { echo "$dir exists"; exit 1; }
    mkdir -p "$dir"
    printf '# %s\n\n## Question\n\n## What would answer it\n\n## Result\n' "{{name}}" > "$dir/README.md"
    printf '"""%s: writes its result under .loupe/, never prints it."""\n' "{{name}}" > "$dir/run.py"
    echo "created $dir"

# regenerate the UI's API types from the server's OpenAPI schema
api-types:
    uv run python -c "import json; from loupe.server import create_app; print(json.dumps(create_app().openapi(), indent=2))" > apps/web/src/lib/openapi.json
    cd {{web}} && pnpm exec openapi-typescript src/lib/openapi.json -o src/lib/api-types.ts && pnpm exec prettier --write src/lib/api-types.ts src/lib/openapi.json > /dev/null
