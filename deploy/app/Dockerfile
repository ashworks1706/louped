# The public demo: the loupe image with the worked examples' runs baked in, from their --tiny modes
# (small models trained to show each behaviour, run on the CPU). Built from the repo root.
ARG BASE=ghcr.io/ashworks1706/loupe:latest
FROM ${BASE} AS runs
RUN uv sync --locked --no-dev --all-extras
COPY experiments/ /app/experiments/
ENV LOUPE_HOME=/data LOUPE_EXPERIMENTS=/app/experiments MLFLOW_DISABLE_AGENT_HINT=1
RUN for script in refusal-direction/run.py refusal-direction/eval.py sycophancy-pushback/run.py \
        "refusal-finetuning/run.py --steps 20 --save-every 5"; do \
      /app/.venv/bin/python /app/experiments/$script --tiny || exit 1; \
    done

FROM ${BASE}
COPY --from=runs --chown=1000:1000 /data /data
USER 1000
