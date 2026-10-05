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
