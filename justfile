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

# the worked examples end to end on their tiny offline models, into LOUPE_HOME for `just serve`
examples:
    #!/usr/bin/env bash
    set -euo pipefail
    export HF_HUB_OFFLINE=1   # nothing downloads: a model fetch fails instead
    export INSPECT_LOG_DIR="${INSPECT_LOG_DIR:-${LOUPE_HOME:-.loupe}/logs}"
    export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"   # tiny models; threads only contend on a busy CPU
    run() { echo "=== $*"; SECONDS=0; uv run --all-extras python "$@"; echo "=== ${SECONDS}s"; }
    run experiments/refusal-direction/run.py --tiny
    run experiments/refusal-direction/eval.py --tiny
    run experiments/sycophancy-pushback/run.py --tiny
    run experiments/refusal-finetuning/run.py --tiny --steps 20 --save-every 5
    uv run --all-extras python - <<'EOF'
    from collections import Counter
    from loupe import stores
    seen = Counter((r.experiment, r.kind) for r in stores.list_runs())
    want = {("refusal-direction", "analysis"): 1, ("refusal-direction", "eval"): 2,
            ("sycophancy-pushback", "analysis"): 2, ("sycophancy-pushback", "eval"): 9,
            ("refusal-finetuning", "training"): 1, ("refusal-finetuning", "analysis"): 1}
    short = {k: (seen[k], n) for k, n in want.items() if seen[k] < n}
    vectors = {v.name for v in stores.list_vectors()}
    missing = {"refusal.tiny-planted-refusal", "caving.tiny-planted-caving"} - vectors
    assert not short and not missing, f"runs (found, wanted): {short}; vectors missing: {missing}"
    print(f"every example is in the app: {sum(seen.values())} runs, {len(vectors)} vectors")
    EOF

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

# scaffold experiments/<name>/ in a domain (src/loupe/stores/experiments.py lists them), active
new-experiment name domain:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="experiments/{{name}}"
    [ -e "$dir" ] && { echo "$dir exists"; exit 1; }
    uv run python -c "from loupe.stores.experiments import DOMAINS; import sys; d = '{{domain}}'; d in DOMAINS or sys.exit(f'domain {d!r} is not one of {list(DOMAINS)}')"
    mkdir -p "$dir"
    cat > "$dir/README.md" <<'README'
    ---
    domain: {{domain}}
    status: active
    ---

    # {{name}}

    ## Question

    <!-- One sentence that comes out yes or no, or as a number. -->

    ## Observation

    <!-- What failed or bottlenecked, as seen, not as interpreted. -->

    ## Hypotheses

    <!-- What might cause it, including the explanations that compete with yours. -->

    ## Baseline

    <!-- The nearest existing method, and the simplest thing that might already work. -->

    ## Test

    <!-- The controlled comparison that tells the hypotheses apart: conditions, metric, seeds. -->

    ## Stop if

    <!-- The result that weakens the idea or makes it impractical. -->

    ## Run

    ## Result

    ## Next
    README
    printf '"""%s: writes its result under .loupe/, never prints it."""\n' "{{name}}" > "$dir/run.py"
    echo "created $dir"

# regenerate the UI's API types from the server's OpenAPI schema
api-types:
    uv run python -c "import json; from loupe.server import create_app; print(json.dumps(create_app().openapi(), indent=2))" > apps/web/src/lib/openapi.json
    cd {{web}} && pnpm exec openapi-typescript src/lib/openapi.json -o src/lib/api-types.ts && pnpm exec prettier --write src/lib/api-types.ts src/lib/openapi.json > /dev/null

# an attribution graph with circuit-tracer, in its own environment (it pins its transformers), on
# the Circuits page; transcoders are a Hub repo such as mwhanna/qwen3-0.6b-transcoders-lowl0 for
# Qwen/Qwen3-0.6B. Also on the Launch page as loupe circuit
circuit model transcoders prompt slug="graph":
    uv run loupe circuit --model "{{model}}" --transcoders "{{transcoders}}" --prompt "{{prompt}}" --slug "{{slug}}"
