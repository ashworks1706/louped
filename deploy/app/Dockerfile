# The public demo: the loupe image with the scripted demo runs baked in. Built from the repo root.
ARG BASE=ghcr.io/ashworks1706/loupe:latest
FROM ${BASE} AS runs
RUN uv sync --locked --no-dev --extra server --extra evals --extra tracking
COPY experiments/demo-pressure-mock/ /demo/
RUN LOUPE_HOME=/data MLFLOW_DISABLE_AGENT_HINT=1 /app/.venv/bin/python /demo/run.py

FROM ${BASE}
COPY --from=runs --chown=1000:1000 /data /data
USER 1000
