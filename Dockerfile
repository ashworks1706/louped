# louped serve with the UI built in. GPU extras are not included; this image is for reading results.
FROM node:22-slim AS web
WORKDIR /web
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN NEXT_TELEMETRY_DISABLED=1 pnpm build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
RUN uv sync --locked --no-dev --extra server
COPY --from=web /web/out /app/web
ENV LOUPED_HOME=/data
VOLUME /data
EXPOSE 8000
CMD ["/app/.venv/bin/louped", "serve", "--host", "0.0.0.0", "--expose", "--web-dir", "/app/web"]
