from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import os
import re

from google.cloud import bigquery
import yaml


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing env {name}")
    return value


def connect() -> bigquery.Client:
    project = require_env("GCP_PROJECT")
    dataset = require_env("BQ_DATASET")
    location = os.environ.get("BQ_LOCATION", "us-central1").strip() or "us-central1"
    client = bigquery.Client(project=project, location=location)
    client.default_query_job_config = bigquery.QueryJobConfig(
        default_dataset=bigquery.DatasetReference(project, dataset),
    )
    return client


def query(
    client: bigquery.Client,
    statement: str,
    params: list[bigquery.ScalarQueryParameter] | None = None,
) -> bigquery.table.RowIterator:
    job_config = bigquery.QueryJobConfig(query_parameters=list(params or []))
    default = getattr(client, "default_query_job_config", None)
    if default is not None and default.default_dataset is not None:
        job_config.default_dataset = default.default_dataset
    return client.query(statement, job_config=job_config).result()


def _p(name: str, kind: str, value: object) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, kind, value)


def start_run(client: bigquery.Client, job: str) -> str:
    run_id = str(uuid4())
    query(
        client,
        """
        INSERT INTO runs (id, job, status, started_at)
        VALUES (@id, @job, 'running', CURRENT_TIMESTAMP())
        """,
        [_p("id", "STRING", run_id), _p("job", "STRING", job)],
    )
    return run_id


def finish_run(client: bigquery.Client, run_id: str, status: str, detail: str | None) -> None:
    query(
        client,
        """
        UPDATE runs
        SET finished_at = CURRENT_TIMESTAMP(), status = @status, detail = @detail
        WHERE id = @id
        """,
        [_p("status", "STRING", status), _p("detail", "STRING", detail), _p("id", "STRING", run_id)],
    )


def insert_account_snapshot(
    client: bigquery.Client,
    run_id: str,
    equity: Decimal | None,
    cash: Decimal | None,
    buying_power: Decimal | None,
    portfolio_value: Decimal | None,
    open_orders: list[dict[str, str | None]],
) -> None:
    query(
        client,
        """
        INSERT INTO account_snapshots (
            run_id, equity, cash, buying_power, portfolio_value, open_orders
        ) VALUES (
            @run_id, @equity, @cash, @buying_power, @portfolio_value, @open_orders
        )
        """,
        [
            _p("run_id", "STRING", run_id),
            _p("equity", "NUMERIC", equity),
            _p("cash", "NUMERIC", cash),
            _p("buying_power", "NUMERIC", buying_power),
            _p("portfolio_value", "NUMERIC", portfolio_value),
            _p("open_orders", "JSON", json.dumps(open_orders)),
        ],
    )


def insert_position_snapshot(
    client: bigquery.Client,
    run_id: str,
    symbol: str,
    qty: Decimal,
    avg_entry_price: Decimal | None,
    market_value: Decimal | None,
    unrealized_pl: Decimal | None,
    current_price: Decimal | None,
) -> None:
    query(
        client,
        """
        INSERT INTO position_snapshots (
            run_id, symbol, qty, avg_entry_price, market_value, unrealized_pl, current_price
        ) VALUES (
            @run_id, @symbol, @qty, @avg_entry_price, @market_value, @unrealized_pl, @current_price
        )
        """,
        [
            _p("run_id", "STRING", run_id),
            _p("symbol", "STRING", symbol),
            _p("qty", "NUMERIC", qty),
            _p("avg_entry_price", "NUMERIC", avg_entry_price),
            _p("market_value", "NUMERIC", market_value),
            _p("unrealized_pl", "NUMERIC", unrealized_pl),
            _p("current_price", "NUMERIC", current_price),
        ],
    )


# ponytail: streaming insertAll, 500 rows per request, 10MB cap.
# Rows sit in the streaming buffer for up to 90 minutes, so this table is append-only.
# Switch to a load job before adding UPDATE or DELETE.
_CHUNK = 500
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BQ = {
    "uuid": "STRING",
    "string": "STRING",
    "timestamp": "TIMESTAMP",
    "numeric": "NUMERIC",
    "integer": "INT64",
}


def ident(name: str) -> str:
    if _IDENT.fullmatch(name) is None:
        raise RuntimeError(f"bad identifier {name}")
    return name


class DB:

    @staticmethod
    def parse_schema(
        schema: str,
    ) -> list[dict[str, Any]]:
        raw = yaml.safe_load(Path(schema).read_text())
        models = raw.get("models") if isinstance(raw, dict) else None
        if not isinstance(models, list) or not models:
            raise RuntimeError(f"schema has no models: {schema}")
        columns = models[0].get("columns")
        if not isinstance(columns, list) or not columns:
            raise RuntimeError(f"schema has no columns: {schema}")
        return columns

    @staticmethod
    def aware(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def insert(
        client: bigquery.Client,
        table: str,
        columns: list[dict[str, Any]],
        rows: list[tuple[Any, ...]],
    ) -> None:
        if not rows:
            return
        fields = []
        for column in columns:
            kind = str(column["data_type"])
            if kind not in _BQ:
                raise RuntimeError(f"unknown type {kind}")
            fields.append(bigquery.SchemaField(ident(str(column["name"])), _BQ[kind]))
        encoded: list[dict[str, Any]] = []
        width = len(columns)
        for row in rows:
            if len(row) != width:
                raise RuntimeError("row width does not match columns")
            item: dict[str, Any] = {}
            for index, column in enumerate(columns):
                value = row[index]
                if value is not None and str(column["data_type"]) == "uuid":
                    value = str(value)
                item[str(column["name"])] = value
            encoded.append(item)
        target = DB._table(client, table)
        for start in range(0, len(encoded), _CHUNK):
            errors = client.insert_rows(target, encoded[start : start + _CHUNK], selected_fields=fields)
            if errors:
                raise RuntimeError(errors[0])

    @staticmethod
    def latest(
        client: bigquery.Client,
        table: str,
        column: str,
        where: dict[str, Any] | None = None,
    ) -> datetime | None:
        filters = where or {}
        statement = f"SELECT max({ident(column)}) AS latest FROM {ident(table)}"
        params: list[bigquery.ScalarQueryParameter] = []
        if filters:
            parts: list[str] = []
            for name, value in filters.items():
                if not isinstance(value, str):
                    raise RuntimeError(f"filter {name} must be a string")
                key = ident(name)
                parts.append(f"{key} = @{key}")
                params.append(bigquery.ScalarQueryParameter(key, "STRING", value))
            statement += " WHERE " + " AND ".join(parts)
        rows = list(query(client, statement, params))
        if not rows or rows[0][0] is None:
            return None
        return rows[0][0]

    @staticmethod
    def _table(client: bigquery.Client, table: str) -> str:
        default = getattr(client, "default_query_job_config", None)
        dataset = None if default is None else default.default_dataset
        if dataset is None:
            raise RuntimeError("missing default dataset")
        return f"{dataset.project}.{dataset.dataset_id}.{ident(table)}"
