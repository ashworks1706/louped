#!/usr/bin/env bash
# The first five minutes, as a pip user meets them: install the wheel in an empty folder, make a
# project, run its example on the offline tiny model from inside the project, serve, and check the
# UI and the run are there. CI runs it on the wheel it built; locally: just install-check.
set -euo pipefail

wheel=$(realpath "$1")
work=$(mktemp -d)
cd "$work"
echo "checking $wheel in $work"

uv venv -q --python 3.12 .venv
uv pip install -q --python .venv/bin/python "${wheel}[server,tracking,interp,agent]"
# shellcheck disable=SC1091
source .venv/bin/activate

louped init proj
cd proj
for f in louped.toml AGENTS.md .mcp.json .gitignore .claude/skills/new-experiment/SKILL.md \
  experiments/does-pushback-flip-answers/run.py; do
  test -f "$f" || { echo "louped init did not write $f"; exit 1; }
done
grep -qx '.louped/' .gitignore

# from a subfolder: the project is found by its louped.toml, so the run lands in proj/.louped
(cd experiments/does-pushback-flip-answers && python run.py --tiny)
test -f .louped/mlflow.db || { echo "the run did not land in the project's .louped/"; exit 1; }

louped serve --port 8765 >serve.log 2>&1 &
pid=$!
trap 'kill $pid 2>/dev/null || true' EXIT
for _ in $(seq 60); do
  curl -sf localhost:8765/api/health >/dev/null && break
  sleep 1
done
grep -q "UI: .*louped/web" serve.log || { cat serve.log; echo "serve did not find the packaged UI"; exit 1; }
curl -sf localhost:8765/ | grep -qi '<html'
curl -sf localhost:8765/api/experiments | grep -q does-pushback-flip-answers
curl -sf localhost:8765/api/runs | grep -q does-pushback-flip-answers
echo "install check passed"
