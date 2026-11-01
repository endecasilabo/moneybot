import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
import yaml
from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from moneybot.db import (
    apply_schema,
    connect,
    finish_run,
    insert_account_snapshot,
    insert_position_snapshot,
    insert_signal,
    require_env,
    sent_order,
    start_run,
    upsert_order,
)
from moneybot.strategy import decide

NY = ZoneInfo("America/New_York")
LIVE_TRADING_URL = "https://api.alpaca.markets"
# Alpaca rejects CLS inside the last 10 minutes before the close.
CLS_CUTOFF = timedelta(minutes=10)
# ponytail: a SPY trade older than this is delayed data, not a close proxy.
# Upgrade path: read the SIP entitlement from the account and fail at startup.
STALE_TRADE = timedelta(minutes=5)


class Config:
    def __init__(
        self,
        mode: str,
        trading_enabled: bool,
        symbol: str,
        qty: int,
        trend_window: int,
        exit_window: int,
        down_days: int,
        submit_before_close_minutes: int,
        feed: str,
    ) -> None:
        self.mode = mode
        self.trading_enabled = trading_enabled
        self.symbol = symbol
        self.qty = qty
        self.trend_window = trend_window
        self.exit_window = exit_window
        self.down_days = down_days
        self.submit_before_close_minutes = submit_before_close_minutes
        self.feed = feed


def main() -> None:
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "trade":
        guarded("trade", trade_window)
    elif command == "snapshot":
        guarded("snapshot", take_snapshot)
    else:
        raise SystemExit("usage: python -m moneybot trade|snapshot")


def guarded(job: str, fn: Any) -> None:
    cfg = load_config()
    guard_live(cfg)
    with connect() as conn:
        apply_schema(conn, schema_path())
        run_id = start_run(conn, job)
        try:
            status, detail = fn(conn, run_id, cfg)
        except Exception as exc:
            finish_run(conn, run_id, "error", str(exc))
            print(f"{job} status=error detail={exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        finish_run(conn, run_id, status, detail)
        print(f"{job} status={status} detail={detail or ''}")


def trade_window(conn: psycopg.Connection, run_id: int, cfg: Config) -> tuple[str, str]:
    trading, data = alpaca_clients()
    clock = trading.get_clock()
    if not in_submit_window(clock, cfg.submit_before_close_minutes):
        return "skipped", "outside_window"

    session = aware(clock.next_close).astimezone(NY).date()
    closes = completed_closes(fetch_bars(data, cfg, session), session)
    if len(closes) < cfg.trend_window:
        raise RuntimeError(f"insufficient_history bars={len(closes)}")

    trade = latest_trade(fetch_latest(data, cfg.symbol), cfg.symbol)
    price = Decimal(str(trade.price))
    # ponytail: last trade stands in for the closing auction. The auction price can differ.
    # Upgrade path: after the bell, store the official daily close next to this proxy. The MOC cannot be changed once submitted.
    trade_at = aware(trade.timestamp)
    age = aware(clock.timestamp) - trade_at
    if age > STALE_TRADE:
        raise RuntimeError(f"stale_trade age_seconds={int(age.total_seconds())}")

    qty = long_qty(trading, cfg.symbol)
    in_position = qty > 0
    decision = decide(
        closes,
        float(price),
        in_position,
        cfg.trend_window,
        cfg.exit_window,
        cfg.down_days,
    )
    if qty < 0:
        insert_signal(
            conn, run_id, cfg.symbol, session, price, decision, True, "hold", "short_position"
        )
        raise RuntimeError("short_position")
    if in_position and qty != qty.to_integral_value():
        insert_signal(conn, run_id, cfg.symbol, session, price, decision, True)
        raise RuntimeError("fractional_position")

    insert_signal(conn, run_id, cfg.symbol, session, price, decision, in_position)
    print(f"signal {cfg.symbol} {decision.action} {decision.reason} last={price} qty={qty}")

    if decision.action == "hold":
        return "ok", decision.reason
    if decision.action == "buy":
        side_name = "buy"
        side = OrderSide.BUY
        order_qty = cfg.qty
        cash = Decimal(str(trading.get_account().cash))
        if cash < price * Decimal(order_qty):
            return "skipped", "insufficient_cash"
    elif decision.action == "sell":
        if qty <= 0:
            raise RuntimeError("sell_without_position")
        side_name = "sell"
        side = OrderSide.SELL
        order_qty = int(qty)
    else:
        raise RuntimeError(f"unknown action {decision.action}")

    if not cfg.trading_enabled:
        return "skipped", "trading_disabled"

    client_order_id = f"scherman-{cfg.symbol.lower()}-{side_name}-{session.isoformat()}"
    if sent_order(conn, client_order_id):
        return "skipped", "already_submitted"

    request = MarketOrderRequest(
        symbol=cfg.symbol,
        qty=order_qty,
        side=side,
        time_in_force=TimeInForce.CLS,
        client_order_id=client_order_id,
    )
    try:
        order = trading.submit_order(order_data=request)
    except APIError as exc:
        if duplicate_order(exc):
            upsert_order(
                conn,
                client_order_id,
                run_id,
                None,
                cfg.symbol,
                side_name,
                order_qty,
                "duplicate",
                None,
                str(exc),
            )
            return "skipped", "already_submitted"
        upsert_order(
            conn,
            client_order_id,
            run_id,
            None,
            cfg.symbol,
            side_name,
            order_qty,
            "error",
            None,
            str(exc),
        )
        raise

    filled = None if order.filled_avg_price is None else Decimal(str(order.filled_avg_price))
    upsert_order(
        conn,
        client_order_id,
        run_id,
        str(order.id),
        cfg.symbol,
        side_name,
        order_qty,
        enum_value(order.status),
        filled,
        None,
    )
    return "ok", f"submitted:{side_name}:{client_order_id}"


def take_snapshot(conn: psycopg.Connection, run_id: int, cfg: Config) -> tuple[str, str]:
    del cfg
    trading, _data = alpaca_clients()
    account = trading.get_account()
    orders = trading.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100))
    insert_account_snapshot(
        conn,
        run_id,
        decimal_or_none(account.equity),
        decimal_or_none(account.cash),
        decimal_or_none(account.buying_power),
        decimal_or_none(account.portfolio_value),
        [order_payload(order) for order in orders],
    )
    positions = trading.get_all_positions()
    for position in positions:
        insert_position_snapshot(
            conn,
            run_id,
            str(position.symbol),
            Decimal(str(position.qty)),
            decimal_or_none(position.avg_entry_price),
            decimal_or_none(position.market_value),
            decimal_or_none(position.unrealized_pl),
            decimal_or_none(position.current_price),
        )
    return "ok", f"positions={len(positions)}"


def load_config() -> Config:
    path = config_path()
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit(f"config must be a mapping: {path}")
    mode = _text(raw, "mode")
    symbol = _text(raw, "symbol").upper()
    feed = _text(raw, "feed")
    trading_enabled = raw.get("trading_enabled")
    qty = _whole(raw, "qty", 1)
    trend_window = _whole(raw, "trend_window", 2)
    exit_window = _whole(raw, "exit_window", 2)
    down_days = _whole(raw, "down_days", 2)
    submit_before = _whole(raw, "submit_before_close_minutes", 11)
    if not isinstance(trading_enabled, bool):
        raise SystemExit("trading_enabled must be true or false")
    if mode != "live":
        raise SystemExit("mode must be live")
    if not symbol:
        raise SystemExit("symbol is empty")
    if feed != "sip":
        raise SystemExit("feed must be sip")
    if submit_before <= 10:
        raise SystemExit("submit_before_close_minutes must be > 10")
    return Config(
        mode,
        trading_enabled,
        symbol,
        qty,
        trend_window,
        exit_window,
        down_days,
        submit_before,
        feed,
    )


def guard_live(cfg: Config) -> None:
    if cfg.mode != "live":
        raise SystemExit("mode must be live")
    base = os.environ.get("APCA_API_BASE_URL", LIVE_TRADING_URL)
    if "paper" in base.lower():
        raise SystemExit("paper URL refused")


def alpaca_clients() -> tuple[TradingClient, StockHistoricalDataClient]:
    key = require_env("ALPACA_KEY")
    secret = require_env("ALPACA_SECRET")
    # alpaca-py defaults paper=True. Both flags are required so a missed kwarg cannot point at paper.
    trading = TradingClient(key, secret, paper=False, url_override=LIVE_TRADING_URL)
    data = StockHistoricalDataClient(key, secret)
    return trading, data


def in_submit_window(clock: Any, minutes: int) -> bool:
    delta = aware(clock.next_close) - aware(clock.timestamp)
    return CLS_CUTOFF < delta <= timedelta(minutes=minutes)


def fetch_bars(data: StockHistoricalDataClient, cfg: Config, session: date) -> list[Any]:
    start = datetime.combine(
        session - timedelta(days=cfg.trend_window * 3),
        datetime.min.time(),
        tzinfo=NY,
    )
    request = StockBarsRequest(
        symbol_or_symbols=cfg.symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=datetime.combine(session, datetime.min.time(), tzinfo=NY),
        limit=10000,
        adjustment=Adjustment.SPLIT,
        feed=DataFeed.SIP,
    )
    return bars_for(data.get_stock_bars(request), cfg.symbol)


def fetch_latest(data: StockHistoricalDataClient, symbol: str) -> Any:
    request = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.SIP)
    return data.get_stock_latest_trade(request)


def completed_closes(bars: list[Any], session: date) -> list[float]:
    dated: list[tuple[datetime, float]] = []
    for bar in bars:
        stamp = aware(bar.timestamp)
        if stamp.astimezone(NY).date() >= session:
            continue
        dated.append((stamp, float(bar.close)))
    dated.sort(key=lambda item: item[0])
    return [close for _, close in dated]


def bars_for(barset: Any, symbol: str) -> list[Any]:
    data = getattr(barset, "data", None)
    if isinstance(data, dict) and symbol in data:
        return list(data[symbol])
    if isinstance(barset, dict) and symbol in barset:
        return list(barset[symbol])
    raise RuntimeError(f"no bars for {symbol}")


def latest_trade(payload: Any, symbol: str) -> Any:
    data = getattr(payload, "data", None)
    if isinstance(data, dict) and symbol in data:
        return data[symbol]
    if isinstance(payload, dict) and symbol in payload:
        return payload[symbol]
    raise RuntimeError(f"no trade for {symbol}")


def long_qty(trading: TradingClient, symbol: str) -> Decimal:
    try:
        position = trading.get_open_position(symbol)
    except APIError as exc:
        if missing_position(exc):
            return Decimal(0)
        raise
    return Decimal(str(position.qty))


def missing_position(exc: APIError) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 404:
        return True
    text = str(exc).lower()
    return "position does not exist" in text or "40410000" in text


def duplicate_order(exc: APIError) -> bool:
    text = str(exc).lower()
    return "client_order_id" in text and ("unique" in text or "duplicate" in text)


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


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value


def config_path() -> Path:
    return Path(os.environ.get("BOT_CONFIG", "config/bot.yaml"))


def schema_path() -> Path:
    raw = os.environ.get("SCHEMA_PATH")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "schema.sql"


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise SystemExit(f"{key} must be a string")
    return value.strip()


def _whole(raw: dict[str, Any], key: str, minimum: int) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SystemExit(f"{key} must be an integer >= {minimum}")
    return value
