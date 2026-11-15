import unittest

from src.strategy import decide


class DecideTest(unittest.TestCase):
    def test_buy_on_third_down_day_when_flat(self) -> None:
        # Flat account buys when the trend SMA is rising and the last three closes are down.
        decision = decide(
            [10, 20, 19, 18, 17],
            16,
            False,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "buy")
        self.assertEqual(decision.reason, "trend_and_pullback")
        self.assertTrue(decision.trend_ok)
        self.assertTrue(decision.pullback_ok)
        self.assertIsNotNone(decision.sma_trend)
        self.assertIsNotNone(decision.sma_trend_prev)
        assert decision.sma_trend is not None
        assert decision.sma_trend_prev is not None
        self.assertGreater(decision.sma_trend, decision.sma_trend_prev)

    def test_two_down_days_do_not_buy(self) -> None:
        # Two down days are not a pullback, so the flat account holds.
        decision = decide(
            [10, 20, 14, 18, 17],
            16,
            False,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "no_pullback")
        self.assertTrue(decision.trend_ok)
        self.assertFalse(decision.pullback_ok)

    def test_falling_trend_does_not_buy(self) -> None:
        # Three down days still do not buy when the trend SMA is falling.
        decision = decide(
            [30, 20, 19, 18, 17],
            16,
            False,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "trend_off")
        self.assertFalse(decision.trend_ok)
        self.assertTrue(decision.pullback_ok)

    def test_equal_trend_does_not_buy(self) -> None:
        # A flat trend SMA (equal, not rising) blocks the buy.
        decision = decide(
            [16, 20, 19, 18, 17],
            16,
            False,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "trend_off")
        self.assertFalse(decision.trend_ok)

    def test_long_does_not_buy_again(self) -> None:
        # Already long, so a valid buy setup holds instead of buying again.
        decision = decide(
            [10, 20, 19, 18, 17],
            16,
            True,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "in_position")

    def test_long_sells_above_sma_exit(self) -> None:
        # A long position sells when today's close is above the exit SMA.
        decision = decide(
            [10, 11, 12, 13, 14],
            20,
            True,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "sell")
        self.assertEqual(decision.reason, "above_sma_exit")

    def test_long_holds_below_sma_exit(self) -> None:
        # A long position holds while today's close stays at or below the exit SMA.
        decision = decide(
            [10, 11, 12, 13, 14],
            10,
            True,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "in_position")

    def test_flat_does_not_sell(self) -> None:
        # No position, so a close above the exit SMA does not sell.
        decision = decide(
            [10, 11, 12, 13, 14],
            20,
            False,
            trend_window=5,
            exit_window=5,
            down_days=3,
        )
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "no_pullback")

    def test_default_windows_need_200_closes(self) -> None:
        # Default 200-day trend window holds when fewer than 200 closes exist.
        decision = decide([float(n) for n in range(1, 200)], 199, False)
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "insufficient_history")
        self.assertIsNone(decision.sma_trend)


if __name__ == "__main__":
    unittest.main()
