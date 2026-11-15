from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from google.cloud.bigquery import Client

from src.db import DB, require_env


class Bars:
    timestamp_column: str = "ts"
    

    def __init__(
        self,
        symbol: str,
        feed: str,
        table: str,
        timeframe: str,
        schema: str,
    ) -> None:
        if feed != "sip":
            raise RuntimeError("feed must be sip")
        self.symbol = symbol
        self.feed = feed
        self.table = table
        self.timeframe = timeframe
        self.schema = schema
        self.columns = DB.parse_schema(
            schema,
        )
    
    def collect(
        self,
        client: Client,
        run_id: str,
    ) -> int:
        del run_id
        data = StockHistoricalDataClient(
            require_env("ALPACA_KEY"),
            require_env("ALPACA_SECRET"),
        )
        request = StockBarsRequest(
            symbol_or_symbols=self.symbol,
            timeframe=TimeFrame.Hour,
            start=self.cursor(
                DB.latest(
                    client,
                    self.table,
                    self.timestamp_column,
                    {
                        "symbol": self.symbol,
                        "feed": self.feed,
                        "timeframe": self.timeframe,
                    },
                ),
            ),
            end=datetime.now(UTC),
            limit=None,
            adjustment=Adjustment.SPLIT,
            feed=DataFeed.SIP,
        )
        fetched = self.iterator(
            data.get_stock_bars(request),
        )
        rows = list(
            map(
                self.row,
                fetched,
            ),
        )
        DB.insert(
            client,
            self.table,
            self.columns,
            rows,
        )
        return len(rows)

    def cursor(
        self,
        latest: datetime | None,
    ) -> datetime:
        if latest is None:
            return datetime(2016, 1, 1, tzinfo=UTC)
        # Start after the last insert. The same bar is not written again.
        return DB.aware(latest) + timedelta(microseconds=1)

    def row(
        self,
        bar: Any,
    ) -> tuple[Any, ...]:
        return tuple(
            map(
                lambda column: self.value(
                    column,
                    bar,
                ),
                self.columns,
            ),
        )

    def value(
        self,
        column: dict[str, Any],
        bar: Any,
    ) -> Any:
        name = str(column["name"])
        if name == "id":
            return uuid4()
        if name == "symbol":
            return self.symbol
        if name == "feed":
            return self.feed
        if name == "timeframe":
            return self.timeframe
        if name == "ts":
            return DB.aware(bar.timestamp)
        return self.cast(
            str(column["data_type"]),
            getattr(bar, name),
        )

    def cast(
        self,
        kind: str,
        raw: Any,
    ) -> Any:
        if raw is None:
            return None
        if kind == "numeric":
            return Decimal(str(raw))
        if kind == "integer":
            return int(raw)
        if kind == "string":
            return str(raw)
        if kind == "timestamp":
            return DB.aware(raw)
        if kind == "uuid":
            return raw
        raise RuntimeError(f"unknown type {kind}")

    def iterator(
        self,
        barset: Any,
    ) -> list[Any]:
        data = getattr(barset, "data", None)
        if isinstance(data, dict) and self.symbol in data:
            return list(data[self.symbol])
        if isinstance(barset, dict) and self.symbol in barset:
            return list(barset[self.symbol])
        return []
