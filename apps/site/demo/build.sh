#!/usr/bin/env bash
# Make the demo project the site's screenshots and video show: a fresh `louped init` with one
# experiment that re-reads CAA's released results. Its runs are real; nothing is mocked.
#   apps/site/demo/build.sh <folder>
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
out="${1:?usage: build.sh <folder>}"
commit=5dabbbd9a0bca5f25e174501e959de378806aa48

louped init "$out"
cp -r "$here/does-caa-steer-every-item" "$out/experiments/"
cd "$out"
python experiments/does-caa-steer-every-item/run.py
louped source add "https://raw.githubusercontent.com/nrimsky/CAA/$commit/README.md" \
  --key caa --title "Steering Llama 2 with Contrastive Activation Addition (code and data)"

# what the agent adds in the video: a column, a chart and a Labels tab on every run
run=$(python -c "from louped.stores.mlflow_runs import list_runs
print(next(r.id for r in list_runs() if r.experiment == 'does-caa-steer-every-item'))")
mkdir -p experiments/does-caa-steer-every-item/derive
cp "$here/agent/derive/"*.py experiments/does-caa-steer-every-item/derive/
louped derive "$run" experiments/does-caa-steer-every-item/derive/slope.py --name slope
louped derive "$run" experiments/does-caa-steer-every-item/derive/slope_by_answer.py --name slope-by-answer
echo '{"parts": {"items/column/slope.slope": {"label": "slope"}}}' \
  > experiments/does-caa-steer-every-item/layout.json
cp -r "$here/agent/plugins" .
