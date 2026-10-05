# The site's demo

The screenshots and the video on the landing page come from a real louped project. Nothing in them
is mocked.

The project has one experiment, `does-caa-steer-every-item`. Its script reads the result files
that the CAA authors released for Llama 2 7B Chat (github.com/nrimsky/CAA, at a pinned commit). It
logs them as louped records and figures. No model runs, so the script needs no GPU.

| File                         | What it does                                                  |
| ---------------------------- | ------------------------------------------------------------- |
| `does-caa-steer-every-item/` | The experiment: its README and `run.py`                       |
| `build.sh <folder>`          | `louped init`, then the experiment, its run and one source    |
| `capture.mjs <app> <out>`    | The screenshots, in light and dark                            |
| `record.mjs <app> <out>`     | One pass through the app: the frames, pointer, clicks, camera |
| `render.py <rec> <out.mp4>`  | The video: the frames in a window, the camera, the pointer    |
| `make.sh`                    | All of the above, into `apps/site/public/demo/`               |

To remake them:

```sh
just web-build
just site-demo
```

`make.sh` needs Chromium for Playwright (or `PW_CHROMIUM` set to one), ffmpeg with libx264, and
Pillow. The script fetches the results from raw.githubusercontent.com.
