# louped. `just` lists every recipe.

set dotenv-load := false

# nothing phones home: no Next.js telemetry, no MLflow agent hints
export NEXT_TELEMETRY_DISABLED := "1"
export MLFLOW_DISABLE_AGENT_HINT := "1"

web := "apps/web"
site := "apps/site"

default:
    @just --list

# first run: Python and UI dependencies, git hooks
bootstrap: setup
    uv run pre-commit install --hook-type pre-commit --hook-type pre-push

# install everything, locked
setup:
    uv sync --locked --all-extras
    cd {{web}} && pnpm install --frozen-lockfile
    cd {{site}} && pnpm install --frozen-lockfile

# the gate: CI and the hooks run exactly this
check: check-python check-web check-site

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

# format, lint, types, static build of the landing page and docs
check-site:
    cd {{site}} && pnpm format:check && pnpm lint && pnpm typecheck && pnpm build

# browser tests against the built UI (run check-web first)
test-e2e:
    cd {{web}} && pnpm test:e2e

# format everything in place
fmt:
    uv run ruff format .
    uv run ruff check --fix .
    cd {{web}} && pnpm format
    cd {{site}} && pnpm format

# the API and the UI on :8000; rebuilds the UI so it always serves current code
serve *args:
    just web-build
    uv run louped serve {{args}}

# the UI dev server on :3000, against the API on :8000
web:
    cd {{web}} && pnpm dev

# build the UI's static export into apps/web/out
web-build:
    cd {{web}} && pnpm build

# the first five minutes as a pip user: build the wheel with its UI, install it in an empty folder,
# louped init, the example, louped serve (scripts/install-check.sh)
install-check: web-build
    rm -rf dist && uv build --wheel
    bash scripts/install-check.sh dist/*.whl

# the landing page and docs on :3001
site:
    cd {{site}} && pnpm dev

# remake the landing page's screenshots and demo video from a fresh demo project (apps/site/demo)
site-demo:
    uv run --with pillow bash apps/site/demo/make.sh

# the louped image
image:
    docker build -t louped .

# re-resolve uv.lock after changing pyproject.toml
lock:
    uv lock

# regenerate the UI's API types from the server's OpenAPI schema
api-types:
    uv run python -c "import json; from louped.server import create_app; print(json.dumps(create_app().openapi(), indent=2))" > apps/web/src/lib/openapi.json
    cd {{web}} && pnpm exec openapi-typescript src/lib/openapi.json -o src/lib/api-types.ts && pnpm exec prettier --write src/lib/api-types.ts src/lib/openapi.json > /dev/null
