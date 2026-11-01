import os
import unittest
from datetime import datetime, timedelta, timezone

from moneybot.main import guard_live, in_submit_window, load_config


class Clock:
    def __init__(self, minutes: int) -> None:
        self.timestamp = datetime(2026, 1, 5, 20, 0, tzinfo=timezone.utc)
        self.next_close = self.timestamp + timedelta(minutes=minutes)


class WindowTest(unittest.TestCase):
    def test_open_edge_is_inside(self) -> None:
        self.assertTrue(in_submit_window(Clock(11), 20))
        self.assertTrue(in_submit_window(Clock(20), 20))

    def test_cutoff_and_early_are_outside(self) -> None:
        self.assertFalse(in_submit_window(Clock(10), 20))
        self.assertFalse(in_submit_window(Clock(21), 20))
        self.assertFalse(in_submit_window(Clock(240), 20))


class ConfigTest(unittest.TestCase):
    def test_repo_config_stays_disarmed(self) -> None:
        previous = os.environ.pop("BOT_CONFIG", None)
        try:
            cfg = load_config()
        finally:
            if previous is not None:
                os.environ["BOT_CONFIG"] = previous
        self.assertEqual(cfg.mode, "live")
        self.assertFalse(cfg.trading_enabled)
        self.assertEqual(cfg.symbol, "SPY")
        self.assertEqual(cfg.qty, 1)
        self.assertEqual(cfg.feed, "sip")
        self.assertEqual(cfg.submit_before_close_minutes, 20)

    def test_paper_url_is_refused(self) -> None:
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
