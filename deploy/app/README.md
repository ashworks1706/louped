# app

The public demo at app.<domain>: `loupe serve` over the scripted runs in
`experiments/demo-pressure-mock`, with no model loaded, so nothing on it can run or write.

The release workflow pushes it as `ghcr.io/ashworks1706/loupe/demo`. Locally:

```sh
just images && docker run --rm -p 8000:8000 loupe-demo
```

## Hosting

A Hugging Face Space (free CPU): create a Docker Space and push the two files in `space/`.
Use the Space URL, or run the image on any container host behind app.<domain>; it only needs
port 8000.
