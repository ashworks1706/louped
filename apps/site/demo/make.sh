#!/usr/bin/env bash
# Remake the site's screenshots and demo video from a fresh demo project (just site-demo).
# Needs the built UI (just web-build), Chromium for Playwright, ffmpeg and Pillow.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
public="$here/../public/demo"
port=8765
app="http://127.0.0.1:$port"
tmp="$(mktemp -d)"

"$here/build.sh" "$tmp/project"
(cd "$tmp/project" && exec louped serve --port "$port") &
server=$!
trap 'kill "$server"; rm -rf "$tmp"' EXIT
until curl -sf -o /dev/null "$app/api/runs"; do sleep 1; done

node "$here/capture.mjs" "$app" "$public"
node "$here/record.mjs" "$app" "$tmp/recording"
python "$here/render.py" "$tmp/recording" "$public/demo.mp4"
ffmpeg -loglevel error -y -ss 1 -i "$public/demo.mp4" -frames:v 1 -q:v 3 "$public/demo-poster.jpg"
