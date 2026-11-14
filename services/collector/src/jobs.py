from decimal import Decimal
from pathlib import Path
from typing import Any
import sys
import os

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.client import TradingClient
from google.cloud.bigquery import Client
import yaml

from src.bars import Bars
from src.db import (
    connect,
    finish_run,
    insert_account_snapshot,
    insert_position_snapshot,
    require_env,
    start_run,
)

LIVE_TRADING_URL = "https://api.alpaca.markets"


class Config:
    def __init__(self, mode: str, symbol: str, feed: str) -> None:
        self.mode = mode
        self.symbol = symbol
        self.feed = feed


def guarded(job: str, fn: Any) -> None:
    cfg = load_config()
    guard_live(cfg)
    with connect() as client:
        run_id = start_run(client, job)
        try:
            status, detail = fn(client, run_id, cfg)
        except Exception as exc:
            finish_run(client, run_id, "error", str(exc))
            print(f"{job} status=error detail={exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        finish_run(client, run_id, status, detail)
        print(f"{job} status={status} detail={detail or ''}")


def take_snapshot(client: Client, run_id: str, cfg: Config) -> tuple[str, str]:
    del cfg
    trading = alpaca_trading()
    account = trading.get_account()
    orders = trading.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100))
    insert_account_snapshot(
        client,
        run_id,
        decimal_or_none(account.equity),
        decimal_or_none(account.cash),
        decimal_or_none(account.buying_power),
        decimal_or_none(account.portfolio_value),
        [order_payload(order) for order in orders],
    )
    positions = trading.get_all_positions()
    # list() forces the lazy map to insert. map alone stores nothing.
    list(
        map(
            lambda position: insert_position_snapshot(
                client,
                run_id,
                str(position.symbol),
                Decimal(str(position.qty)),
                decimal_or_none(position.avg_entry_price),
                decimal_or_none(position.market_value),
                decimal_or_none(position.unrealized_pl),
                decimal_or_none(position.current_price),
            ),
            positions,
        ),
    )
    return "ok", f"positions={len(positions)}"


def store_bars(client: Client, run_id: str, cfg: Config) -> tuple[str, str]:
    count = Bars(
        cfg.symbol,
        cfg.feed,
        "base_bar",
        "1Hour",
        "dbt/models/base/base_bar.yml",
    ).collect(
        client,
        run_id,
    )
    return "ok", f"bars={count}"


def load_config() -> Config:
    path = config_path()
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit(f"config must be a mapping: {path}")
    mode = _text(raw, "mode")
    symbol = _text(raw, "symbol").upper()
    feed = _text(raw, "feed")
    if mode != "live":
        raise SystemExit("mode must be live")
    if not symbol:
        raise SystemExit("symbol is empty")
    if feed != "sip":
        raise SystemExit("feed must be sip")
    return Config(mode, symbol, feed)


def guard_live(cfg: Config) -> None:
    if cfg.mode != "live":
        raise SystemExit("mode must be live")
    base = os.environ.get("APCA_API_BASE_URL", LIVE_TRADING_URL)
    if "paper" in base.lower():
        raise SystemExit("paper URL refused")


def alpaca_trading() -> TradingClient:
    key = require_env("ALPACA_KEY")
    secret = require_env("ALPACA_SECRET")
    # alpaca-py defaults paper=True. Both flags are required so a missed kwarg cannot point at paper.
    return TradingClient(key, secret, paper=False, url_override=LIVE_TRADING_URL)


def order_payload(order: Any) -> dict[str, str | None]:
    qty = None if order.qty is None else str(order.qty)
    return {
        "id": str(order.id),
        "client_order_id": None if order.client_order_id is None else str(order.client_order_id),
        "symbol": str(order.symbol),
        "side": enum_value(order.side),
        "qty": qty,
        "type": enum_value(order.type),
        "time_in_force": enum_value(order.time_in_force),
        "status": enum_value(order.status),
    }


def enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def config_path() -> Path:
    return Path(os.environ.get("BOT_CONFIG", "config/bot.yml"))


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise SystemExit(f"{key} must be a string")
    return value.strip()
