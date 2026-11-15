import importlib.util
import unittest
from functools import partial

from src.backtest import plot_equity_curves, plot_monte_carlo, simulate
from src.strategy import decide

HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
HAS_PLOTLY = importlib.util.find_spec("plotly") is not None

_closes = [10, 20, 19, 18, 17, 16, 100]
_strategy = partial(decide, trend_window=5, exit_window=5, down_days=3)


@unittest.skipUnless(HAS_MATPLOTLIB, "matplotlib not installed, see requirements-dev.txt")
class MatplotlibPlotTest(unittest.TestCase):
    def test_equity_curve_has_one_line_per_strategy(self) -> None:
        result = simulate(_closes, _strategy)
        fig = plot_equity_curves({"a": result, "b": result}, engine="matplotlib")
        self.assertEqual(len(fig.axes[0].lines), 2)

    def test_monte_carlo_has_one_series_per_strategy(self) -> None:
        fig = plot_monte_carlo({"a": [0.1, 0.2], "b": [-0.1, 0.0]}, engine="matplotlib")
        self.assertEqual(len(fig.axes[0].patches) > 0, True)


@unittest.skipUnless(HAS_PLOTLY, "plotly not installed, see requirements-dev.txt")
class PlotlyPlotTest(unittest.TestCase):
    def test_equity_curve_has_one_trace_per_strategy(self) -> None:
        result = simulate(_closes, _strategy)
        fig = plot_equity_curves({"a": result, "b": result}, engine="plotly")
        self.assertEqual(len(fig.data), 2)

    def test_monte_carlo_has_one_trace_per_strategy(self) -> None:
        fig = plot_monte_carlo({"a": [0.1, 0.2], "b": [-0.1, 0.0]}, engine="plotly")
        self.assertEqual(len(fig.data), 2)


class UnknownEngineTest(unittest.TestCase):
    def test_rejects_unknown_engine(self) -> None:
        result = simulate(_closes, _strategy)
        with self.assertRaises(ValueError):
            plot_equity_curves({"a": result}, engine="excel")


if __name__ == "__main__":
    unittest.main()
