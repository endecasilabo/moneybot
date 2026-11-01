import unittest

from moneybot.strategy import decide


class DecideTest(unittest.TestCase):
    def test_buy_on_third_down_day_when_flat(self) -> None:
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
        decision = decide([float(n) for n in range(1, 200)], 199, False)
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "insufficient_history")
        self.assertIsNone(decision.sma_trend)


if __name__ == "__main__":
    unittest.main()
