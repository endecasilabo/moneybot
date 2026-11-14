from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
import unittest
import os

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "dbt/models/base/base_bar.yml"
CONFIG = ROOT / "config/bot.yml"

from src.jobs import guard_live, load_config
from src.bars import Bars


class Quote:
    def __init__(self) -> None:
        self.timestamp = datetime(2026, 11, 6, 20, 30, tzinfo=UTC)
        self.open = 1
        self.high = 2
        self.low = 0.5
        self.close = 1.5
        self.volume = 10
        self.trade_count = 3
        self.vwap = 1.4


def sample_bars() -> Bars:
    return Bars(
        "SPY",
        "sip",
        "base_bar",
        "1Hour",
        str(SCHEMA),
    )


class BarsCursorTest(unittest.TestCase):
    def test_cursor_uses_history_or_the_stored_bar(self) -> None:
        # No stored bar starts the backfill. A stored bar is skipped so insert does not write it again.
        bars = sample_bars()
        self.assertEqual(bars.cursor(None), datetime(2016, 1, 1, tzinfo=UTC))
        stored = datetime(2026, 11, 6, 20, 30, tzinfo=timezone.utc)
        self.assertEqual(bars.cursor(stored), stored + timedelta(microseconds=1))

    def test_row_follows_schema(self) -> None:
        # Column order and types come from base_bar.yml.
        bars = sample_bars()
        row = dict(zip((column["name"] for column in bars.columns), bars.row(Quote())))
        self.assertIsInstance(row["id"], UUID)
        self.assertEqual(row["symbol"], "SPY")
        self.assertEqual(row["feed"], "sip")
        self.assertEqual(row["timeframe"], "1Hour")
        self.assertEqual(row["ts"], Quote().timestamp)
        self.assertEqual(row["close"], Decimal("1.5"))
        self.assertEqual(row["trade_count"], 3)


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_config = os.environ.get("BOT_CONFIG")
        os.environ["BOT_CONFIG"] = str(CONFIG)

    def tearDown(self) -> None:
        if self.previous_config is None:
            os.environ.pop("BOT_CONFIG", None)
        else:
            os.environ["BOT_CONFIG"] = self.previous_config

    def test_repo_config_stays_disarmed(self) -> None:
        # Checked-in config stays live, SPY, sip feed.
        cfg = load_config()
        self.assertEqual(cfg.mode, "live")
        self.assertEqual(cfg.symbol, "SPY")
        self.assertEqual(cfg.feed, "sip")

    def test_paper_url_is_refused(self) -> None:
        # A paper Alpaca base URL makes guard_live exit.
        previous = os.environ.get("APCA_API_BASE_URL")
        os.environ["APCA_API_BASE_URL"] = "https://paper-api.alpaca.markets"
        try:
            with self.assertRaises(SystemExit):
                guard_live(load_config())
        finally:
            if previous is None:
                os.environ.pop("APCA_API_BASE_URL", None)
            else:
                os.environ["APCA_API_BASE_URL"] = previous


if __name__ == "__main__":
    unittest.main()
