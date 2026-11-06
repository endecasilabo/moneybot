# Build context is the repo root: docker build -f app/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/entrypoint.py ./entrypoint.py
COPY src ./src
COPY config ./config

ENV BOT_CONFIG=/app/config/bot.yml
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/app/entrypoint.py"]
