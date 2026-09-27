# apps/web

loupe's UI: a Next.js static export served by `loupe serve`. Design rules are in `AGENTS.md`.

```
pnpm dev          dev server on :3000, API expected on :8000 (.env.development)
pnpm build        static export into out/
pnpm test:e2e     Playwright on out/, screenshots in test-results/
```
