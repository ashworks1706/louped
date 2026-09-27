# loupe. `just` lists every recipe.

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

# the API on :8000, serving the built UI when there is one
serve *args:
    uv run loupe serve {{args}}

# the UI dev server on :3000, against the API on :8000
web:
    cd {{web}} && pnpm dev

# build the UI's static export into apps/web/out
web-build:
    cd {{web}} && pnpm build

# the landing page and docs on :3001
site:
    cd {{site}} && pnpm dev

# the loupe image, and the public demo on top of it
images:
    docker build -t loupe .
    docker build -f deploy/app/Dockerfile --build-arg BASE=loupe -t loupe-demo .

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

# an attribution graph with circuit-tracer, in its own environment (it pins transformers 4.57),
# into <home>/graphs with its viewer, which loupe serves on the Circuits page; transcoders are a
# Hub repo such as mwhanna/gemma-scope-transcoders for google/gemma-2-2b
circuit model transcoders prompt slug="graph":
    #!/usr/bin/env bash
    set -euo pipefail
    graphs="$(uv run python -c 'from loupe.core import graphs_dir; print(graphs_dir())')"
    ct=(uvx --from circuit-tracer==0.5.0)
    "${ct[@]}" circuit-tracer attribute -m "{{model}}" -t "{{transcoders}}" -p "{{prompt}}" \
        --slug "{{slug}}" --graph_file_dir "$graphs"
    uv run python -c 'from loupe.core import capture; print(capture().model_dump_json(indent=2))' \
        > "$graphs/{{slug}}.meta.json"
    assets="$("${ct[@]}" python -c 'import circuit_tracer.frontend as f, pathlib; print(pathlib.Path(f.__file__).parent / "assets")')"
    rm -rf "$graphs/viewer" && cp -r "$assets" "$graphs/viewer"
    echo "open /circuits/?slug={{slug}} in loupe"

# a local Neuronpedia in Docker (built on first run); loupe's SAE feature links then open it
neuronpedia port="3100":
    NEURONPEDIA_PORT={{port}} docker compose -f deploy/neuronpedia/compose.yaml up -d --build --wait
    uv run python -c 'from loupe.core import home; p = home() / "neuronpedia"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("http://localhost:{{port}}")'
    echo "http://localhost:{{port}}"

# features for one SAE into the local Neuronpedia, e.g. gpt2-small 6-res-jb (ids as on neuronpedia.org)
neuronpedia-import model source port="3100":
    curl -fsSN "http://localhost:{{port}}/api/admin/import?modelId={{model}}&sourceId={{source}}"

# stop the local Neuronpedia; its database stays in a Docker volume
neuronpedia-down:
    docker compose -f deploy/neuronpedia/compose.yaml down
    uv run python -c 'from loupe.core import home; (home() / "neuronpedia").unlink(missing_ok=True)'
