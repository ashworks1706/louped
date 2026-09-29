# app

The public demo: `loupe serve` over the worked examples' runs, from their `--tiny` modes (small
models trained to show each behaviour), with no model loaded, so nothing on it can run or write.

The release workflow pushes it as `ghcr.io/ashworks1706/loupe/demo`. Locally:

```sh
just images && docker run --rm -p 8000:8000 loupe-demo
```

On a Hugging Face Space (free CPU), create a Docker Space and push the two files in `space/`.
