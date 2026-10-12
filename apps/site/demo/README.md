# The site's demo

The screenshots and the video on the landing page come from real louped projects. The video runs
from install to result: `record.mjs` runs `uv tool install louped`, `louped init` and `louped serve`
in a scratch folder and shows their own output, then works in that fresh project. The app, its
pages and its numbers are real, and so is the run: the agent's actions go through the API its tools
call (`new_experiment`, `launch`, `derive`, `set_part`, `ui_show`, `ui_selection`,
`save_cohort`). The files the agent writes on request (a column, a chart, a Labels page) are in
`agent/`. The agent's side of the
conversation is scripted: `record.mjs` holds its lines. The video plays at 1.25x, and waits faster still, marked.

The project has one experiment, `does-caa-steer-every-item`. Its script reads the result files
that the CAA authors released for Llama 2 7B Chat (github.com/nrimsky/CAA, at a pinned commit). It
logs them as louped records and figures. No model runs, so the script needs no GPU.

| File                         | What it does                                                       |
| ---------------------------- | ------------------------------------------------------------------ |
| `does-caa-steer-every-item/` | The experiment: its README and `run.py`                            |
| `agent/`                     | What the agent adds: two derive scripts and a Labels plugin        |
| `build.sh <folder>`          | `louped init`, the experiment, its run, a source, what agent/ adds |
| `capture.mjs <app> <out>`    | The screenshots, in light and dark                                 |
| `record.mjs <out>`           | The scenario: terminal, frames, pointer, camera, agent lines       |
| `render.py <rec> <out.mp4>`  | The video: the app in a window beside the agent's panel            |
| `make.sh`                    | All of the above, into `apps/site/public/demo/`                    |

To remake them:

```sh
just web-build
just site-demo
```

`make.sh` needs uv, port 8000 free, Chromium for Playwright (or `PW_CHROMIUM` set to one), ffmpeg
with libx264, and Pillow. The scripts fetch the results from raw.githubusercontent.com.
