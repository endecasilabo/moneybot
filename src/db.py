import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from google.cloud import bigquery

from src.strategy import Decision

# Every table is append-only: a state change is a new row, and the *_latest views give the
# current state. BigQuery has no enforced keys and slow, conflicting UPDATEs; see
# brain/architecture/0003-bigquery.md.


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing env {name}")
    return value


def connect() -> bigquery.Client:
    project, _, dataset = require_env("BQ_DATASET").partition(".")
    if not dataset:
        raise SystemExit("BQ_DATASET must be <project>.<dataset>")
    return bigquery.Client(project=project)


def table(name: str) -> str:
    return f"{require_env('BQ_DATASET')}.{name}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def insert(conn: bigquery.Client, name: str, row: dict[str, Any]) -> None:
    errors = conn.insert_rows_json(table(name), [{k: json_value(v) for k, v in row.items()}])
    if errors:
        raise RuntimeError(f"bigquery insert into {name} failed: {errors}")


def start_run(conn: bigquery.Client, job: str) -> str:
    run_id = str(uuid.uuid4())
    insert(conn, "runs", {"run_id": run_id, "job": job, "event_ts": now(), "status": "running"})
    return run_id


def finish_run(
    conn: bigquery.Client, run_id: str, job: str, status: str, detail: str | None
) -> None:
    insert(
        conn,
        "runs",
        {"run_id": run_id, "job": job, "event_ts": now(), "status": status, "detail": detail},
    )


def insert_signal(
    conn: bigquery.Client,
    run_id: str,
    symbol: str,
    session_date: date,
    last_price: Decimal,
    decision: Decision,
    in_position: bool,
    action: str | None = None,
    reason: str | None = None,
    *,
    params: dict[str, Any],
) -> None:
    insert(
        conn,
        "signals",
        {
            "signal_id": str(uuid.uuid4()),
            "run_id": run_id,
            "ts": now(),
            "symbol": symbol,
            "session_date": session_date,
            "last_price": last_price,
            "sma_trend": decision.sma_trend,
            "sma_trend_prev": decision.sma_trend_prev,
            "sma_exit": decision.sma_exit,
            "trend_ok": decision.trend_ok,
            "pullback_ok": decision.pullback_ok,
            "in_position": in_position,
            "action": decision.action if action is None else action,
            "reason": decision.reason if reason is None else reason,
            "params": params,
        },
    )


def sent_order(conn: bigquery.Client, client_order_id: str) -> bool:
    query = (
        f"SELECT 1 FROM `{table('orders')}` WHERE client_order_id = @id "
        "AND (alpaca_order_id IS NOT NULL OR status = 'duplicate') LIMIT 1"
    )
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("id", "STRING", client_order_id)]
    )
    return any(True for _ in conn.query(query, job_config=config).result())


def record_order(
    conn: bigquery.Client,
    client_order_id: str,
    run_id: str,
    alpaca_order_id: str | None,
    symbol: str,
    side: str,
    qty: int,
    status: str | None,
    filled_avg_price: Decimal | None,
    error: str | None,
) -> None:
    insert(
        conn,
        "orders",
        {
            "client_order_id": client_order_id,
            "run_id": run_id,
            "event_ts": now(),
            "alpaca_order_id": alpaca_order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "time_in_force": "cls",
            "status": status,
            "filled_avg_price": filled_avg_price,
            "error": error,
        },
    )


def insert_account_snapshot(
    conn: bigquery.Client,
    run_id: str,
    equity: Decimal | None,
    cash: Decimal | None,
    buying_power: Decimal | None,
    portfolio_value: Decimal | None,
    open_orders: list[dict[str, str | None]],
) -> None:
    insert(
        conn,
        "account_snapshots",
        {
            "run_id": run_id,
            "ts": now(),
            "equity": equity,
            "cash": cash,
            "buying_power": buying_power,
            "portfolio_value": portfolio_value,
            "open_orders": open_orders,
        },
    )


def insert_position_snapshot(
    conn: bigquery.Client,
    run_id: str,
    symbol: str,
    qty: Decimal,
    avg_entry_price: Decimal | None,
    market_value: Decimal | None,
    unrealized_pl: Decimal | None,
    current_price: Decimal | None,
) -> None:
    insert(
        conn,
        "position_snapshots",
        {
            "run_id": run_id,
            "ts": now(),
            "symbol": symbol,
            "qty": qty,
            "avg_entry_price": avg_entry_price,
            "market_value": market_value,
            "unrealized_pl": unrealized_pl,
            "current_price": current_price,
        },
    )
