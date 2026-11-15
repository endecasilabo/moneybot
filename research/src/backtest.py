import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from src.strategy import Decision, decide

NY = ZoneInfo("America/New_York")


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing env {name}")
    return value


def load_local_env() -> None:
    # python-dotenv is optional. Exported vars win over .env.
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


def bars_for(barset: Any, symbol: str) -> list[Any]:
    data = getattr(barset, "data", None)
    if isinstance(data, dict) and symbol in data:
        return list(data[symbol])
    if isinstance(barset, dict) and symbol in barset:
        return list(barset[symbol])
    raise RuntimeError(f"no bars for {symbol}")

Side = str  # "buy" | "sell"
# A strategy is anything that looks at completed history + today's proxy + current position
# and returns a Decision — decide() with fixed params (via functools.partial) or a different
# algorithm entirely.
Strategy = Callable[[list[float], float, bool], Decision]


@dataclass(frozen=True)
class Trade:
    side: Side
    index: int
    price: float


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    final_return: float
    num_trades: int
    win_rate: float
    max_drawdown: float
    equity_curve: list[float]


def simulate(closes: list[float], strategy: Strategy) -> BacktestResult:
    """Walk-forward replay of `strategy` over closes. closes[i] is treated as today's close
    proxy on day i, closes[:i] as the completed history, same contract as src.jobs.
    A strategy that needs more history than it has (e.g. decide() below its trend_window)
    just holds — simulate() doesn't second-guess how much history a strategy needs."""
    if not closes:
        raise ValueError("closes is empty")

    equity = 1.0
    entry_price = 0.0
    in_position = False
    trades: list[Trade] = []
    equity_curve = [equity]
    peak = equity
    max_drawdown = 0.0

    for i in range(1, len(closes)):
        today = closes[i]
        decision = strategy(closes[:i], today, in_position)
        if decision.action == "buy" and not in_position:
            in_position, entry_price = True, today
            trades.append(Trade("buy", i, today))
        elif decision.action == "sell" and in_position:
            equity *= today / entry_price
            in_position = False
            trades.append(Trade("sell", i, today))

        mark = equity * today / entry_price if in_position else equity
        equity_curve.append(mark)
        peak = max(peak, mark)
        max_drawdown = max(max_drawdown, (peak - mark) / peak)

    sells = [t for t in trades if t.side == "sell"]
    buys = [t for t in trades if t.side == "buy"]
    wins = sum(1 for buy, sell in zip(buys, sells) if sell.price > buy.price)
    win_rate = wins / len(sells) if sells else 0.0
    return BacktestResult(trades, equity_curve[-1] - 1.0, len(sells), win_rate, max_drawdown, equity_curve)


def _validate_shares_args(qty: int | str, initial_capital: float, max_allocation: float = 1.0) -> None:
    if isinstance(qty, bool) or (isinstance(qty, int) and qty <= 0):
        raise ValueError("qty must be a positive int or 'auto'")
    if qty != "auto" and not isinstance(qty, int):
        raise ValueError("qty must be a positive int or 'auto'")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if not (0.0 < max_allocation <= 1.0):
        raise ValueError("max_allocation must be in (0, 1]")


def simulate_shares(
    closes: list[float],
    strategy: Strategy,
    qty: int | str = "auto",
    initial_capital: float = 10_000.0,
    max_allocation: float = 1.0,
) -> BacktestResult:
    """Same walk-forward replay as simulate(), but sized the way src.jobs actually trades:
    whole shares bought from a real cash balance, never 100% of equity reinvested fractionally.
    qty="auto" (default): buy as many whole shares as `cash * max_allocation` affords —
    max_allocation=1.0 (default) spends all available cash, a lower value (e.g. 0.5) always
    leaves the rest as a cash buffer instead of going all-in on one signal. qty=N: always buy
    exactly N shares (src.jobs's literal cfg.qty, e.g. qty=1 to replicate the repo's
    default config exactly) — max_allocation is unused in that mode, there's no cash target to
    cap. Either way: no margin, no fractional shares, whole position sold at exit. equity_curve
    is in dollars (starting at initial_capital), not simulate()'s x1 multiplier."""
    if not closes:
        raise ValueError("closes is empty")
    _validate_shares_args(qty, initial_capital, max_allocation)

    cash = initial_capital
    position_qty = 0
    in_position = False
    trades: list[Trade] = []
    equity_curve = [cash]
    peak = cash
    max_drawdown = 0.0

    for i in range(1, len(closes)):
        today = closes[i]
        decision = strategy(closes[:i], today, in_position)
        if decision.action == "buy" and not in_position:
            shares = int((cash * max_allocation) // today) if qty == "auto" else qty
            if shares > 0 and cash >= today * shares:
                cash -= today * shares
                position_qty = shares
                in_position = True
                trades.append(Trade("buy", i, today))
            # else: insufficient_cash, same as src.jobs.trade_window — skip, no trade.
        elif decision.action == "sell" and in_position:
            cash += today * position_qty
            position_qty = 0
            in_position = False
            trades.append(Trade("sell", i, today))

        mark = cash + position_qty * today
        equity_curve.append(mark)
        peak = max(peak, mark)
        max_drawdown = max(max_drawdown, (peak - mark) / peak)

    sells = [t for t in trades if t.side == "sell"]
    buys = [t for t in trades if t.side == "buy"]
    wins = sum(1 for buy, sell in zip(buys, sells) if sell.price > buy.price)
    win_rate = wins / len(sells) if sells else 0.0
    final_return = (equity_curve[-1] - initial_capital) / initial_capital
    return BacktestResult(trades, final_return, len(sells), win_rate, max_drawdown, equity_curve)


def _resample_path(closes: list[float], rng: random.Random) -> list[float]:
    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    path = [closes[0]]
    for _ in returns:
        path.append(path[-1] * (1 + rng.choice(returns)))
    return path


def monte_carlo(
    closes: list[float],
    strategy: Strategy,
    trials: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Bootstraps daily returns from closes (i.i.d. resampling) into synthetic future paths
    and returns the final_return of each. Not a model of real SPY dynamics, just a stress
    test of the strategy against reshuffled historical volatility."""
    rng = random.Random(seed)
    return [simulate(_resample_path(closes, rng), strategy).final_return for _ in range(trials)]


def monte_carlo_shares(
    closes: list[float],
    strategy: Strategy,
    qty: int | str = "auto",
    initial_capital: float = 10_000.0,
    max_allocation: float = 1.0,
    trials: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Same resampling as monte_carlo(), sized through simulate_shares() instead of
    simulate()."""
    rng = random.Random(seed)
    return [
        simulate_shares(_resample_path(closes, rng), strategy, qty, initial_capital, max_allocation).final_return
        for _ in range(trials)
    ]


def benchmark(closes: list[float], strategies: dict[str, Strategy]) -> list[tuple[str, BacktestResult]]:
    """Runs simulate() for each named strategy and ranks by final_return. A strategy can be a
    different parameterization of decide() (functools.partial) or a different algorithm."""
    ranked = [(name, simulate(closes, strategy)) for name, strategy in strategies.items()]
    return sorted(ranked, key=lambda item: item[1].final_return, reverse=True)


def benchmark_shares(
    closes: list[float],
    strategies: dict[str, Strategy],
    qty: int | str = "auto",
    initial_capital: float = 10_000.0,
    max_allocation: float = 1.0,
) -> list[tuple[str, BacktestResult]]:
    """Same as benchmark(), sized through simulate_shares() instead of simulate() — all
    strategies share the same qty/initial_capital/max_allocation, so the comparison stays
    apples-to-apples."""
    ranked = [
        (name, simulate_shares(closes, strategy, qty, initial_capital, max_allocation))
        for name, strategy in strategies.items()
    ]
    return sorted(ranked, key=lambda item: item[1].final_return, reverse=True)


class HasEquityCurve(Protocol):
    equity_curve: list[float]


def plot_equity_curves(results: dict[str, HasEquityCurve], engine: str = "matplotlib"):
    """Overlays the equity curve of each named result — BacktestResult, PortfolioResult
    (src.portfolio), or anything else with an equity_curve field. engine is "matplotlib"
    (returns a Figure — fig.savefig(path)) or "plotly" (returns a Figure — fig.write_html(path)).
    Imports its plotting library lazily: neither is in requirements.txt, only in
    requirements-dev.txt, so importing src.backtest itself never requires them."""
    if engine == "matplotlib":
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        for name, result in results.items():
            ax.plot(result.equity_curve, label=name)
        ax.set_xlabel("day")
        ax.set_ylabel("equity")
        ax.legend()
        return fig
    if engine == "plotly":
        import plotly.graph_objects as go

        fig = go.Figure()
        for name, result in results.items():
            fig.add_trace(go.Scatter(y=result.equity_curve, name=name, mode="lines"))
        fig.update_layout(xaxis_title="day", yaxis_title="equity")
        return fig
    raise ValueError(f"unknown engine {engine!r}, use 'matplotlib' or 'plotly'")


def plot_monte_carlo(outcomes: dict[str, list[float]], engine: str = "matplotlib"):
    """Overlaid histogram of monte_carlo() final_return outcomes, one series per named
    strategy. Same engine/import contract as plot_equity_curves."""
    if engine == "matplotlib":
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        for name, values in outcomes.items():
            ax.hist(values, bins=30, alpha=0.5, label=name)
        ax.set_xlabel("final_return")
        ax.set_ylabel("trials")
        ax.legend()
        return fig
    if engine == "plotly":
        import plotly.graph_objects as go

        fig = go.Figure()
        for name, values in outcomes.items():
            fig.add_trace(go.Histogram(x=values, name=name, opacity=0.5))
        fig.update_layout(barmode="overlay", xaxis_title="final_return", yaxis_title="trials")
        return fig
    raise ValueError(f"unknown engine {engine!r}, use 'matplotlib' or 'plotly'")


def fetch_history(symbol: str, start: date, end: date, feed: DataFeed = DataFeed.SIP) -> list[float]:
    """Read-only historical daily closes from Alpaca. Needs ALPACA_KEY/ALPACA_SECRET but never
    submits an order — safe against a live account. Prints the ACTUAL first/last bar dates, not
    the requested start/end: Alpaca's SIP entitlement silently clips `start` to however far back
    its history goes (e.g. ~10.8 years), so a request for 2010 can quietly come back as 2015."""
    client = StockHistoricalDataClient(require_env("ALPACA_KEY"), require_env("ALPACA_SECRET"))
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=datetime.combine(start, datetime.min.time(), tzinfo=NY),
        end=datetime.combine(end, datetime.min.time(), tzinfo=NY),
        limit=10000,
        adjustment=Adjustment.SPLIT,
        feed=feed,
    )
    bars = sorted(bars_for(client.get_stock_bars(request), symbol), key=lambda bar: bar.timestamp)
    if not bars:
        raise RuntimeError(f"no bars for {symbol} between {start} and {end}")
    actual_start = bars[0].timestamp.date()
    note = f" (asked for {start}, Alpaca's earliest is {actual_start})" if actual_start > start else ""
    print(f"{symbol}: {len(bars)} closes, {actual_start} to {bars[-1].timestamp.date()}{note}")
    return [float(bar.close) for bar in bars]


def report(result: BacktestResult) -> str:
    return (
        f"return={result.final_return:.2%} trades={result.num_trades} "
        f"win_rate={result.win_rate:.0%} max_drawdown={result.max_drawdown:.2%}"
    )


def save_plot(fig, engine: str, name: str) -> None:
    path = f"{name}.png" if engine == "matplotlib" else f"{name}.html"
    fig.savefig(path) if engine == "matplotlib" else fig.write_html(path)
    print(f"saved {path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["backtest", "montecarlo", "benchmark"])
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--shares", action="store_true",
        help="size with real whole shares from a cash balance (src.jobs-style) instead of 100%% fractional reinvestment",
    )
    parser.add_argument(
        "--qty", default="auto",
        help="with --shares: 'auto' (buy as many whole shares as cash affords, default) or a literal share count",
    )
    parser.add_argument("--initial-capital", type=float, default=10_000.0, help="with --shares only")
    parser.add_argument(
        "--max-allocation", type=float, default=1.0,
        help="with --shares and --qty auto: cap on the fraction of cash spent per entry (default 1.0 = all of it)",
    )
    parser.add_argument("--plot", choices=["matplotlib", "plotly"], default=None)
    args = parser.parse_args()
    load_local_env()
    qty: int | str = args.qty if args.qty == "auto" else int(args.qty)

    history = fetch_history(args.symbol, date.fromisoformat(args.start), date.fromisoformat(args.end))
    scherman = partial(decide, trend_window=200, exit_window=5, down_days=3)

    if args.mode == "backtest":
        result = (
            simulate_shares(history, scherman, qty, args.initial_capital, args.max_allocation)
            if args.shares
            else simulate(history, scherman)
        )
        print(report(result))
        if args.plot:
            save_plot(plot_equity_curves({"scherman": result}, args.plot), args.plot, "backtest")
    elif args.mode == "montecarlo":
        outcomes = sorted(
            monte_carlo_shares(
                history, scherman, qty, args.initial_capital, args.max_allocation,
                trials=args.trials, seed=args.seed,
            )
            if args.shares
            else monte_carlo(history, scherman, trials=args.trials, seed=args.seed)
        )
        p5, median, p95 = (
            outcomes[int(len(outcomes) * 0.05)],
            outcomes[len(outcomes) // 2],
            outcomes[int(len(outcomes) * 0.95) - 1],
        )
        print(f"trials={len(outcomes)} p5={p5:.2%} median={median:.2%} p95={p95:.2%}")
        if args.plot:
            save_plot(plot_monte_carlo({"scherman": outcomes}, args.plot), args.plot, "montecarlo")
    else:
        strategies: dict[str, Strategy] = {
            "default": scherman,
            "faster_exit": partial(decide, trend_window=200, exit_window=3, down_days=3),
            "shorter_trend": partial(decide, trend_window=100, exit_window=5, down_days=3),
            "patient_entry": partial(decide, trend_window=200, exit_window=5, down_days=4),
        }
        ranked = (
            benchmark_shares(history, strategies, qty, args.initial_capital, args.max_allocation)
            if args.shares
            else benchmark(history, strategies)
        )
        for name, result in ranked:
            print(f"{name}: {report(result)}")
        if args.plot:
            curves = {name: result for name, result in ranked}
            save_plot(plot_equity_curves(curves, args.plot), args.plot, "benchmark")
