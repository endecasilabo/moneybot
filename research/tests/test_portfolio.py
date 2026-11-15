import random
import unittest
from functools import partial

from src.backtest import monte_carlo, simulate, simulate_shares
from src.portfolio import (
    _resample_paths,
    _weights_for,
    monte_carlo_portfolio,
    monte_carlo_portfolio_shares,
    simulate_portfolio,
    simulate_portfolio_shares,
)
from src.strategy import decide

_scherman = partial(decide, trend_window=5, exit_window=5, down_days=3)
_closes = [10, 20, 19, 18, 17, 16, 100]


class SimulatePortfolioTest(unittest.TestCase):
    def test_single_symbol_matches_single_asset_simulate(self) -> None:
        solo = simulate(_closes, _scherman)
        portfolio = simulate_portfolio({"A": _closes}, _scherman, weighting="equal")
        self.assertAlmostEqual(portfolio.final_return, solo.final_return)
        self.assertEqual(portfolio.num_trades, solo.num_trades)

    def test_two_identical_symbols_equal_weight_tracks_either_one(self) -> None:
        # If equal-weight didn't normalize by the active count (e.g. gave both symbols
        # weight 1.0 instead of 0.5 each), this would double-count the shared return and
        # diverge from the single-asset result.
        result = simulate_portfolio({"A": _closes, "B": _closes}, _scherman, weighting="equal")
        solo = simulate(_closes, _scherman)
        self.assertAlmostEqual(result.final_return, solo.final_return)

    def test_misaligned_closes_raise(self) -> None:
        with self.assertRaises(ValueError):
            simulate_portfolio({"A": _closes, "B": _closes[:-1]}, _scherman)

    def test_empty_closes_raise(self) -> None:
        with self.assertRaises(ValueError):
            simulate_portfolio({}, _scherman)


class SimulatePortfolioSharesTest(unittest.TestCase):
    def test_two_identical_symbols_auto_matches_single_asset_auto(self) -> None:
        # Splitting $1000 equal-weight between two identical symbols should end up buying
        # the same total shares (and reaching the same final_return) as putting the whole
        # $1000 into one of them with simulate_shares(qty="auto") — same economics either way.
        solo = simulate_shares(_closes, _scherman, qty="auto", initial_capital=1000.0)
        portfolio = simulate_portfolio_shares(
            {"A": _closes, "B": _closes}, _scherman, weighting="equal", qty="auto", initial_capital=1000.0
        )
        self.assertAlmostEqual(portfolio.final_return, solo.final_return)

    def test_literal_qty_buys_that_many_shares_per_entry_regardless_of_weighting(self) -> None:
        result = simulate_portfolio_shares(
            {"A": _closes, "B": _closes}, _scherman, qty=1, initial_capital=1000.0
        )
        buys = [t for t in result.trades if t.side == "buy"]
        self.assertEqual(len(buys), 2)
        self.assertEqual({t.symbol for t in buys}, {"A", "B"})

    def test_insufficient_cash_caps_shares_bought(self) -> None:
        # $20 isn't enough for either symbol's $16-a-share target weight times two, so
        # whatever gets bought must still respect the cash actually on hand.
        result = simulate_portfolio_shares(
            {"A": _closes, "B": _closes}, _scherman, weighting="equal", qty="auto", initial_capital=20.0
        )
        spent = sum(t.price for t in result.trades if t.side == "buy")
        self.assertLessEqual(spent, 20.0)

    def test_misaligned_closes_raise(self) -> None:
        with self.assertRaises(ValueError):
            simulate_portfolio_shares({"A": _closes, "B": _closes[:-1]}, _scherman)

    def test_empty_closes_raise(self) -> None:
        with self.assertRaises(ValueError):
            simulate_portfolio_shares({}, _scherman)


class MonteCarloPortfolioSharesTest(unittest.TestCase):
    def test_reproducible_with_seed(self) -> None:
        closes = {"A": _closes, "B": [c * 1.5 for c in _closes]}
        first = monte_carlo_portfolio_shares(closes, _scherman, trials=5, seed=3)
        second = monte_carlo_portfolio_shares(closes, _scherman, trials=5, seed=3)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)

    def test_misaligned_closes_raise(self) -> None:
        with self.assertRaises(ValueError):
            monte_carlo_portfolio_shares({"A": _closes, "B": _closes[:-1]}, _scherman)


class MonteCarloPortfolioTest(unittest.TestCase):
    def test_resample_paths_keeps_symbols_synchronized(self) -> None:
        # B's price is always exactly 2x A's (identical % returns every day). If resampling
        # picked a day independently per symbol instead of once for the whole portfolio, this
        # ratio would drift — it only stays exactly 2.0 if both get the same resampled day.
        a = [100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0]
        b = [price * 2 for price in a]
        paths = _resample_paths({"A": a, "B": b}, random.Random(1))
        ratios = [pb / pa for pa, pb in zip(paths["A"], paths["B"])]
        for ratio in ratios:
            self.assertAlmostEqual(ratio, 2.0)

    def test_single_symbol_matches_single_asset_monte_carlo(self) -> None:
        closes = [100.0 + i for i in range(10)]
        solo = monte_carlo(closes, _scherman, trials=5, seed=1)
        portfolio = monte_carlo_portfolio({"A": closes}, _scherman, trials=5, seed=1)
        self.assertEqual(portfolio, solo)

    def test_reproducible_with_seed(self) -> None:
        closes = {"A": _closes, "B": [c * 1.5 for c in _closes]}
        first = monte_carlo_portfolio(closes, _scherman, trials=5, seed=7)
        second = monte_carlo_portfolio(closes, _scherman, trials=5, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)

    def test_misaligned_closes_raise(self) -> None:
        with self.assertRaises(ValueError):
            monte_carlo_portfolio({"A": _closes, "B": _closes[:-1]}, _scherman)


class WeightsForTest(unittest.TestCase):
    def test_equal_splits_evenly(self) -> None:
        weights = _weights_for(["A", "B", "C"], {}, 0, "equal", 20)
        self.assertEqual(weights, {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})

    def test_no_active_symbols_returns_empty(self) -> None:
        self.assertEqual(_weights_for([], {}, 0, "equal", 20), {})

    def test_inverse_vol_favors_the_calmer_symbol(self) -> None:
        calm = [100.0, 100.5, 100.2, 100.6, 100.3, 100.7]
        volatile = [100.0, 110.0, 95.0, 115.0, 90.0, 120.0]
        closes = {"calm": calm, "volatile": volatile}
        weights = _weights_for(["calm", "volatile"], closes, 5, "inverse_vol", vol_window=5)
        self.assertGreater(weights["calm"], weights["volatile"])
        self.assertAlmostEqual(weights["calm"] + weights["volatile"], 1.0)

    def test_unknown_weighting_raises(self) -> None:
        with self.assertRaises(ValueError):
            _weights_for(["A"], {"A": [1.0, 2.0]}, 1, "market_cap", 20)


if __name__ == "__main__":
    unittest.main()
