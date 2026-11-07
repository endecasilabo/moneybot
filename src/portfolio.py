import random
from dataclasses import dataclass
from functools import partial

from src.backtest import (
    Strategy,
    _validate_shares_args,
    fetch_history,
    load_local_env,
    plot_equity_curves,
    plot_monte_carlo,
    report,
    save_plot,
)
from src.strategy import decide

Weighting = str  # "equal" | "inverse_vol"


@dataclass(frozen=True)
class PortfolioTrade:
    symbol: str
    side: str  # "buy" | "sell"
    index: int
    price: float


@dataclass(frozen=True)
class PortfolioResult:
    trades: list[PortfolioTrade]
    final_return: float
    num_trades: int
    win_rate: float
    max_drawdown: float
    equity_curve: list[float]


def simulate_portfolio(
    closes: dict[str, list[float]],
    strategy: Strategy,
    weighting: Weighting = "equal",
    vol_window: int = 20,
) -> PortfolioResult:
    """Runs `strategy` independently per symbol (same in/out timing as simulate() in
    src.backtest) and, after each day's signals, reweights capital among whatever symbols
    are currently long. Rebalances every day a position could have changed, not on a fixed
    calendar — that's the natural cadence for a signal-driven entry/exit, not a periodic one."""
    if not closes:
        raise ValueError("closes is empty")
    length = len(next(iter(closes.values())))
    if any(len(series) != length for series in closes.values()):
        raise ValueError("all symbols must have the same number of closes (aligned calendar)")
    if length < 2:
        raise ValueError("need at least 2 closes per symbol")

    in_position = {symbol: False for symbol in closes}
    weights: dict[str, float] = {}
    trades: list[PortfolioTrade] = []
    equity = 1.0
    equity_curve = [equity]
    peak = equity
    max_drawdown = 0.0

    for i in range(1, length):
        day_return = sum(
            weight * (closes[symbol][i] / closes[symbol][i - 1] - 1.0)
            for symbol, weight in weights.items()
        )
        equity *= 1.0 + day_return
        equity_curve.append(equity)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)

        for symbol, series in closes.items():
            decision = strategy(series[:i], series[i], in_position[symbol])
            if decision.action == "buy" and not in_position[symbol]:
                in_position[symbol] = True
                trades.append(PortfolioTrade(symbol, "buy", i, series[i]))
            elif decision.action == "sell" and in_position[symbol]:
                in_position[symbol] = False
                trades.append(PortfolioTrade(symbol, "sell", i, series[i]))

        active = [symbol for symbol in closes if in_position[symbol]]
        weights = _weights_for(active, closes, i, weighting, vol_window)

    sells = [t for t in trades if t.side == "sell"]
    wins = 0
    for sell in sells:
        entry = next(
            t for t in reversed(trades) if t.symbol == sell.symbol and t.side == "buy" and t.index < sell.index
        )
        wins += sell.price > entry.price
    win_rate = wins / len(sells) if sells else 0.0
    return PortfolioResult(trades, equity_curve[-1] - 1.0, len(sells), win_rate, max_drawdown, equity_curve)


def simulate_portfolio_shares(
    closes: dict[str, list[float]],
    strategy: Strategy,
    weighting: Weighting = "equal",
    qty: int | str = "auto",
    initial_capital: float = 10_000.0,
    vol_window: int = 20,
) -> PortfolioResult:
    """Same per-symbol timing as simulate_portfolio(), but sized with real whole shares from a
    single shared cash pool instead of fractional equity weights — same relationship
    simulate_shares() has to simulate() in src.backtest.

    qty="auto" (default): a new entry's target is `weight * current total equity`, converted
    to whole shares, capped by whatever cash is actually free (never on margin). qty=N: every
    entry buys exactly N shares regardless of weighting — there's no dollar target to size
    against, so `weighting` is unused in that mode.

    Existing positions are never trimmed to free cash for a new entrant — same no-partial-
    position discipline src.jobs has for a single symbol, extended to a portfolio."""
    if not closes:
        raise ValueError("closes is empty")
    length = len(next(iter(closes.values())))
    if any(len(series) != length for series in closes.values()):
        raise ValueError("all symbols must have the same number of closes (aligned calendar)")
    if length < 2:
        raise ValueError("need at least 2 closes per symbol")
    _validate_shares_args(qty, initial_capital)

    cash = initial_capital
    position_qty = {symbol: 0 for symbol in closes}
    in_position = {symbol: False for symbol in closes}
    trades: list[PortfolioTrade] = []
    equity_curve = [cash]
    peak = cash
    max_drawdown = 0.0

    for i in range(1, length):
        today_price = {symbol: series[i] for symbol, series in closes.items()}
        decisions = {
            symbol: strategy(series[:i], today_price[symbol], in_position[symbol])
            for symbol, series in closes.items()
        }

        for symbol, decision in decisions.items():
            if decision.action == "sell" and in_position[symbol]:
                cash += today_price[symbol] * position_qty[symbol]
                position_qty[symbol] = 0
                in_position[symbol] = False
                trades.append(PortfolioTrade(symbol, "sell", i, today_price[symbol]))

        buying = [symbol for symbol, decision in decisions.items() if decision.action == "buy" and not in_position[symbol]]
        if buying:
            held = [symbol for symbol in closes if in_position[symbol]]
            equity_now = cash + sum(position_qty[symbol] * today_price[symbol] for symbol in held)
            weights = _weights_for(held + buying, closes, i, weighting, vol_window) if qty == "auto" else {}
            for symbol in buying:
                price = today_price[symbol]
                shares = int((weights[symbol] * equity_now) // price) if qty == "auto" else qty
                shares = min(shares, int(cash // price)) if qty == "auto" else shares
                if shares > 0 and cash >= price * shares:
                    cash -= price * shares
                    position_qty[symbol] = shares
                    in_position[symbol] = True
                    trades.append(PortfolioTrade(symbol, "buy", i, price))

        mark = cash + sum(position_qty[symbol] * today_price[symbol] for symbol in closes)
        equity_curve.append(mark)
        peak = max(peak, mark)
        max_drawdown = max(max_drawdown, (peak - mark) / peak)

    sells = [t for t in trades if t.side == "sell"]
    wins = 0
    for sell in sells:
        entry = next(
            t for t in reversed(trades) if t.symbol == sell.symbol and t.side == "buy" and t.index < sell.index
        )
        wins += sell.price > entry.price
    win_rate = wins / len(sells) if sells else 0.0
    final_return = (equity_curve[-1] - initial_capital) / initial_capital
    return PortfolioResult(trades, final_return, len(sells), win_rate, max_drawdown, equity_curve)


def monte_carlo_portfolio(
    closes: dict[str, list[float]],
    strategy: Strategy,
    weighting: Weighting = "equal",
    vol_window: int = 20,
    trials: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Same bootstrap idea as monte_carlo() in src.backtest, generalized to several
    symbols: each synthetic day picks ONE historical day and applies that day's return to
    every symbol at once, so whatever correlation existed between symbols on that real day
    is preserved. Resampling each symbol independently would scramble the cross-asset
    correlation a diversified portfolio depends on, making the result meaningless."""
    if not closes:
        raise ValueError("closes is empty")
    length = len(next(iter(closes.values())))
    if any(len(series) != length for series in closes.values()):
        raise ValueError("all symbols must have the same number of closes (aligned calendar)")

    rng = random.Random(seed)
    results = []
    for _ in range(trials):
        paths = _resample_paths(closes, rng)
        results.append(simulate_portfolio(paths, strategy, weighting, vol_window).final_return)
    return results


def monte_carlo_portfolio_shares(
    closes: dict[str, list[float]],
    strategy: Strategy,
    weighting: Weighting = "equal",
    qty: int | str = "auto",
    initial_capital: float = 10_000.0,
    vol_window: int = 20,
    trials: int = 1000,
    seed: int | None = None,
) -> list[float]:
    """Same cross-symbol-synchronized resampling as monte_carlo_portfolio(), sized through
    simulate_portfolio_shares() instead of simulate_portfolio()."""
    if not closes:
        raise ValueError("closes is empty")
    length = len(next(iter(closes.values())))
    if any(len(series) != length for series in closes.values()):
        raise ValueError("all symbols must have the same number of closes (aligned calendar)")

    rng = random.Random(seed)
    results = []
    for _ in range(trials):
        paths = _resample_paths(closes, rng)
        results.append(
            simulate_portfolio_shares(paths, strategy, weighting, qty, initial_capital, vol_window).final_return
        )
    return results


def _resample_paths(closes: dict[str, list[float]], rng: random.Random) -> dict[str, list[float]]:
    symbols = list(closes.keys())
    length = len(closes[symbols[0]])
    returns = {
        symbol: [closes[symbol][i] / closes[symbol][i - 1] - 1.0 for i in range(1, length)]
        for symbol in symbols
    }
    num_days = length - 1
    paths = {symbol: [closes[symbol][0]] for symbol in symbols}
    for _ in range(num_days):
        day = rng.randrange(num_days)
        for symbol in symbols:
            paths[symbol].append(paths[symbol][-1] * (1 + returns[symbol][day]))
    return paths


def _weights_for(
    active: list[str],
    closes: dict[str, list[float]],
    today: int,
    weighting: Weighting,
    vol_window: int,
) -> dict[str, float]:
    if not active:
        return {}
    if weighting == "equal":
        share = 1.0 / len(active)
        return {symbol: share for symbol in active}
    if weighting == "inverse_vol":
        inv_vols = {symbol: _inverse_volatility(closes[symbol][: today + 1], vol_window) for symbol in active}
        total = sum(inv_vols.values())
        if total == 0.0:
            share = 1.0 / len(active)
            return {symbol: share for symbol in active}
        return {symbol: inv_vol / total for symbol, inv_vol in inv_vols.items()}
    raise ValueError(f"unknown weighting {weighting!r}, use 'equal' or 'inverse_vol'")


def _inverse_volatility(closes: list[float], window: int) -> float:
    tail = closes[-(window + 1) :]
    if len(tail) < 2:
        return 0.0
    returns = [tail[j] / tail[j - 1] - 1.0 for j in range(1, len(tail))]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    volatility = variance**0.5
    return 0.0 if volatility == 0.0 else 1.0 / volatility


if __name__ == "__main__":
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["backtest", "montecarlo"])
    parser.add_argument("--symbols", default="SPY,TLT,GLD", help="comma-separated, e.g. SPY,TLT,GLD")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--weighting", choices=["equal", "inverse_vol"], default="equal")
    parser.add_argument("--vol-window", type=int, default=20)
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--shares", action="store_true",
        help="size with real whole shares from a shared cash pool (src.jobs-style) instead of fractional equity weights",
    )
    parser.add_argument(
        "--qty", default="auto",
        help="with --shares: 'auto' (buy each entry's target weight in whole shares, capped by free cash, default) or a literal share count per entry",
    )
    parser.add_argument("--initial-capital", type=float, default=10_000.0, help="with --shares only")
    parser.add_argument("--plot", choices=["matplotlib", "plotly"], default=None)
    args = parser.parse_args()
    load_local_env()
    qty: int | str = args.qty if args.qty == "auto" else int(args.qty)

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    closes = {symbol: fetch_history(symbol, start, end) for symbol in symbols}

    scherman = partial(decide, trend_window=200, exit_window=5, down_days=3)

    if args.mode == "backtest":
        result = (
            simulate_portfolio_shares(closes, scherman, args.weighting, qty, args.initial_capital, args.vol_window)
            if args.shares
            else simulate_portfolio(closes, scherman, weighting=args.weighting, vol_window=args.vol_window)
        )
        print(f"[{args.weighting}] {report(result)}")
        if args.plot:
            save_plot(plot_equity_curves({args.weighting: result}, args.plot), args.plot, "portfolio")
    else:
        outcomes = sorted(
            monte_carlo_portfolio_shares(
                closes, scherman, args.weighting, qty, args.initial_capital, args.vol_window,
                trials=args.trials, seed=args.seed,
            )
            if args.shares
            else monte_carlo_portfolio(
                closes, scherman, weighting=args.weighting, vol_window=args.vol_window,
                trials=args.trials, seed=args.seed,
            )
        )
        p5, median, p95 = (
            outcomes[int(len(outcomes) * 0.05)],
            outcomes[len(outcomes) // 2],
            outcomes[int(len(outcomes) * 0.95) - 1],
        )
        print(f"[{args.weighting}] trials={len(outcomes)} p5={p5:.2%} median={median:.2%} p95={p95:.2%}")
        if args.plot:
            save_plot(
                plot_monte_carlo({args.weighting: outcomes}, args.plot), args.plot, "portfolio_montecarlo"
            )
