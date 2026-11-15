import unittest
from functools import partial

from src.backtest import (
    benchmark,
    benchmark_shares,
    monte_carlo,
    monte_carlo_shares,
    simulate,
    simulate_shares,
)
from src.strategy import Decision, decide


def scherman(trend_window: int = 5, exit_window: int = 5, down_days: int = 3):
    return partial(decide, trend_window=trend_window, exit_window=exit_window, down_days=down_days)


def never_trade(closes: list[float], last: float, in_position: bool) -> Decision:
    return Decision("hold", None, None, None, False, False, "manual")


class SimulateTest(unittest.TestCase):
    def test_buy_then_sell_tracks_equity(self) -> None:
        result = simulate([10, 20, 19, 18, 17, 16, 100], scherman())
        self.assertEqual([t.side for t in result.trades], ["buy", "sell"])
        self.assertAlmostEqual(result.final_return, 5.25)
        self.assertEqual(result.num_trades, 1)
        self.assertEqual(result.win_rate, 1.0)
        self.assertEqual(result.max_drawdown, 0.0)

    def test_no_signal_stays_flat(self) -> None:
        result = simulate([10, 11, 12, 13, 14, 13], scherman())
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_return, 0.0)

    def test_strategy_below_its_own_window_just_holds(self) -> None:
        result = simulate([1.0, 2.0, 3.0], scherman(trend_window=5))
        self.assertEqual(result.trades, [])

    def test_empty_closes_raises(self) -> None:
        with self.assertRaises(ValueError):
            simulate([], scherman())

    def test_a_non_decide_strategy_can_be_simulated_too(self) -> None:
        result = simulate([10, 20, 19, 18, 17, 16, 100], never_trade)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_return, 0.0)


class SimulateSharesTest(unittest.TestCase):
    def test_auto_buys_as_many_whole_shares_as_cash_allows(self) -> None:
        # Same buy@16/sell@100 as test_buy_then_sell_tracks_equity. With $1000 and a $16
        # share, "auto" affords 62 shares ($992, $8 left idle) — close to simulate()'s
        # 525% (100% fractional reinvestment), not identical, because of that rounding.
        result = simulate_shares([10, 20, 19, 18, 17, 16, 100], scherman(), qty="auto", initial_capital=1000.0)
        self.assertEqual([t.side for t in result.trades], ["buy", "sell"])
        self.assertAlmostEqual(result.final_return, 5.208)
        self.assertEqual(result.equity_curve[-1], 6208.0)

    def test_max_allocation_caps_auto_sizing_below_full_cash(self) -> None:
        # Same trade, capped at 50% of cash: int(500 // 16) = 31 shares instead of 62.
        result = simulate_shares(
            [10, 20, 19, 18, 17, 16, 100], scherman(), qty="auto", initial_capital=1000.0, max_allocation=0.5
        )
        self.assertAlmostEqual(result.final_return, 2.604)
        self.assertEqual(result.equity_curve[-1], 3604.0)

    def test_max_allocation_out_of_range_rejected(self) -> None:
        with self.assertRaises(ValueError):
            simulate_shares([10.0, 11.0], scherman(), max_allocation=0.0)
        with self.assertRaises(ValueError):
            simulate_shares([10.0, 11.0], scherman(), max_allocation=1.5)

    def test_literal_qty_buys_exactly_that_many_shares_not_all_capital(self) -> None:
        # qty=1 on $1000 — src.jobs's actual default config, deliberately tiny.
        result = simulate_shares([10, 20, 19, 18, 17, 16, 100], scherman(), qty=1, initial_capital=1000.0)
        self.assertAlmostEqual(result.final_return, 0.084)
        self.assertEqual(result.equity_curve[-1], 1084.0)

    def test_literal_qty_scales_the_same_trade_linearly(self) -> None:
        result = simulate_shares([10, 20, 19, 18, 17, 16, 100], scherman(), qty=2, initial_capital=1000.0)
        self.assertAlmostEqual(result.final_return, 0.168)

    def test_insufficient_cash_skips_the_buy(self) -> None:
        result = simulate_shares([10, 20, 19, 18, 17, 16, 100], scherman(), qty=1, initial_capital=10.0)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_return, 0.0)

    def test_auto_with_too_little_cash_for_one_share_also_skips(self) -> None:
        result = simulate_shares([10, 20, 19, 18, 17, 16, 100], scherman(), qty="auto", initial_capital=10.0)
        self.assertEqual(result.trades, [])

    def test_rejects_non_positive_qty(self) -> None:
        with self.assertRaises(ValueError):
            simulate_shares([10.0, 11.0], scherman(), qty=0)

    def test_rejects_invalid_qty_string(self) -> None:
        with self.assertRaises(ValueError):
            simulate_shares([10.0, 11.0], scherman(), qty="all")

    def test_rejects_non_positive_initial_capital(self) -> None:
        with self.assertRaises(ValueError):
            simulate_shares([10.0, 11.0], scherman(), initial_capital=0.0)


class MonteCarloTest(unittest.TestCase):
    def test_reproducible_with_seed(self) -> None:
        closes = [100.0 + i for i in range(10)]
        strategy = scherman()
        first = monte_carlo(closes, strategy, trials=5, seed=1)
        second = monte_carlo(closes, strategy, trials=5, seed=1)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)


class MonteCarloSharesTest(unittest.TestCase):
    def test_reproducible_with_seed(self) -> None:
        closes = [100.0 + i for i in range(10)]
        strategy = scherman()
        first = monte_carlo_shares(closes, strategy, trials=5, seed=1)
        second = monte_carlo_shares(closes, strategy, trials=5, seed=1)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)


class BenchmarkTest(unittest.TestCase):
    def test_ranks_by_return_descending(self) -> None:
        closes = [10, 20, 19, 18, 17, 16, 100]
        ranked = benchmark(closes, {"a": scherman(), "b": scherman(down_days=4)})
        returns = [result.final_return for _, result in ranked]
        self.assertEqual(returns, sorted(returns, reverse=True))

    def test_compares_different_strategies_not_just_different_params(self) -> None:
        closes = [10, 20, 19, 18, 17, 16, 100]
        ranked = dict(benchmark(closes, {"scherman": scherman(), "never_trade": never_trade}))
        self.assertGreater(ranked["scherman"].num_trades, 0)
        self.assertEqual(ranked["never_trade"].num_trades, 0)


class BenchmarkSharesTest(unittest.TestCase):
    def test_ranks_by_return_descending(self) -> None:
        closes = [10, 20, 19, 18, 17, 16, 100]
        ranked = benchmark_shares(
            closes, {"a": scherman(), "b": scherman(down_days=4)}, qty="auto", initial_capital=1000.0
        )
        returns = [result.final_return for _, result in ranked]
        self.assertEqual(returns, sorted(returns, reverse=True))


if __name__ == "__main__":
    unittest.main()
