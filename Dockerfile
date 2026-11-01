FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema.sql .
COPY config ./config
COPY moneybot ./moneybot

ENV BOT_CONFIG=/app/config/bot.yaml
ENV SCHEMA_PATH=/app/schema.sql
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "moneybot"]
