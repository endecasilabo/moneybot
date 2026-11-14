ARG BEDROCK_IMAGE

FROM python:3.15-slim AS bedrock

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt 

FROM ${BEDROCK_IMAGE} AS app
COPY . .

ENTRYPOINT ["python", "/app/entrypoint.py"]
