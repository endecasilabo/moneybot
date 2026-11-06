import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.types.json import Json

from src.strategy import Decision


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing env {name}")
    return value


def connect() -> psycopg.Connection:
    instance = require_env("INSTANCE_CONNECTION_NAME")
    socket_dir = os.environ.get("CLOUDSQL_DIR", "/cloudsql")
    return psycopg.connect(
        host=str(Path(socket_dir) / instance),
        dbname=require_env("DB_NAME"),
        user=require_env("DB_USER"),
        password=require_env("DB_PASSWORD"),
        connect_timeout=10,
        autocommit=True,
    )


def start_run(conn: psycopg.Connection, job: str) -> int:
    row = conn.execute(
        "INSERT INTO runs (job, status) VALUES (%s, 'running') RETURNING id",
        (job,),
    ).fetchone()
    if row is None:
        raise RuntimeError("run insert returned no id")
    return int(row[0])


def finish_run(conn: psycopg.Connection, run_id: int, status: str, detail: str | None) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = now(), status = %s, detail = %s WHERE id = %s",
        (status, detail, run_id),
    )


def insert_signal(
    conn: psycopg.Connection,
    run_id: int,
    symbol: str,
    session_date: date,
    last_price: Decimal,
    decision: Decision,
    in_position: bool,
    action: str | None = None,
    reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO signals (
            run_id, symbol, session_date, last_price, sma_trend, sma_trend_prev,
            sma_exit, trend_ok, pullback_ok, in_position, action, reason
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            symbol,
            session_date,
            last_price,
            decision.sma_trend,
            decision.sma_trend_prev,
            decision.sma_exit,
            decision.trend_ok,
            decision.pullback_ok,
            in_position,
            decision.action if action is None else action,
            decision.reason if reason is None else reason,
        ),
    )


def sent_order(conn: psycopg.Connection, client_order_id: str) -> bool:
    row = conn.execute(
        "SELECT alpaca_order_id, status FROM orders WHERE client_order_id = %s",
        (client_order_id,),
    ).fetchone()
    if row is None:
        return False
    alpaca_order_id, status = row
    return alpaca_order_id is not None or status == "duplicate"


def upsert_order(
    conn: psycopg.Connection,
    client_order_id: str,
    run_id: int,
    alpaca_order_id: str | None,
    symbol: str,
    side: str,
    qty: int,
    status: str | None,
    filled_avg_price: Decimal | None,
    error: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO orders (
            client_order_id, run_id, alpaca_order_id, symbol, side, qty,
            time_in_force, status, filled_avg_price, error
        ) VALUES (%s, %s, %s, %s, %s, %s, 'cls', %s, %s, %s)
        ON CONFLICT (client_order_id) DO UPDATE SET
            run_id = EXCLUDED.run_id,
            alpaca_order_id = COALESCE(orders.alpaca_order_id, EXCLUDED.alpaca_order_id),
            status = EXCLUDED.status,
            filled_avg_price = COALESCE(EXCLUDED.filled_avg_price, orders.filled_avg_price),
            error = EXCLUDED.error
        """,
        (
            client_order_id,
            run_id,
            alpaca_order_id,
            symbol,
            side,
            qty,
            status,
            filled_avg_price,
            error,
        ),
    )


def insert_account_snapshot(
    conn: psycopg.Connection,
    run_id: int,
    equity: Decimal | None,
    cash: Decimal | None,
    buying_power: Decimal | None,
    portfolio_value: Decimal | None,
    open_orders: list[dict[str, str | None]],
) -> None:
    conn.execute(
        """
        INSERT INTO account_snapshots (
            run_id, equity, cash, buying_power, portfolio_value, open_orders
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (run_id, equity, cash, buying_power, portfolio_value, Json(open_orders)),
    )


def insert_position_snapshot(
    conn: psycopg.Connection,
    run_id: int,
    symbol: str,
    qty: Decimal,
    avg_entry_price: Decimal | None,
    market_value: Decimal | None,
    unrealized_pl: Decimal | None,
    current_price: Decimal | None,
) -> None:
    conn.execute(
        """
        INSERT INTO position_snapshots (
            run_id, symbol, qty, avg_entry_price, market_value, unrealized_pl, current_price
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (run_id, symbol, qty, avg_entry_price, market_value, unrealized_pl, current_price),
    )
