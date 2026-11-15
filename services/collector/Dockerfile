# Build context is the repo root, so the image can carry config/ and the dbt schema the jobs read.
# Allowlist: Dockerfile.dockerignore next to this file.
ARG BEDROCK_IMAGE

FROM python:3.12-slim AS bedrock

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

WORKDIR /app

COPY services/collector/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

FROM ${BEDROCK_IMAGE} AS app
COPY services/collector/entrypoint.py .
COPY services/collector/src/ src/
COPY config/bot.yml config/bot.yml
COPY dbt/models/base/base_bar.yml dbt/models/base/base_bar.yml

ENTRYPOINT ["python", "/app/entrypoint.py"]
