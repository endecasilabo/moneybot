from dataclasses import dataclass
from typing import Literal

Action = Literal["buy", "sell", "hold"]


@dataclass(frozen=True)
class Decision:
    action: Action
    sma_trend: float | None
    sma_trend_prev: float | None
    sma_exit: float | None
    trend_ok: bool
    pullback_ok: bool
    reason: str


def decide(
    closes: list[float],
    last: float,
    in_position: bool,
    trend_window: int = 200,
    exit_window: int = 5,
    down_days: int = 3,
) -> Decision:
    """Long-only Scherman pattern. `closes` are completed sessions, oldest first. `last` is today's close proxy."""
    if trend_window < 2 or exit_window < 2 or down_days < 2:
        raise ValueError("windows must be >= 2")
    if (
        len(closes) < trend_window
        or len(closes) < down_days
        or len(closes) < exit_window - 1
    ):
        return Decision("hold", None, None, None, False, False, "insufficient_history")

    sma_trend = _mean(closes[-(trend_window - 1) :] + [last])
    sma_trend_prev = _mean(closes[-trend_window:])
    sma_exit = _mean(closes[-(exit_window - 1) :] + [last])
    trend_ok = sma_trend > sma_trend_prev
    pullback_ok = _pullback(closes, last, down_days)

    if in_position:
        if last > sma_exit:
            return Decision(
                "sell", sma_trend, sma_trend_prev, sma_exit, trend_ok, pullback_ok, "above_sma_exit"
            )
        return Decision(
            "hold", sma_trend, sma_trend_prev, sma_exit, trend_ok, pullback_ok, "in_position"
        )
    if trend_ok and pullback_ok:
        return Decision(
            "buy", sma_trend, sma_trend_prev, sma_exit, trend_ok, pullback_ok, "trend_and_pullback"
        )
    if not trend_ok:
        return Decision(
            "hold", sma_trend, sma_trend_prev, sma_exit, trend_ok, pullback_ok, "trend_off"
        )
    return Decision(
        "hold", sma_trend, sma_trend_prev, sma_exit, trend_ok, pullback_ok, "no_pullback"
    )


def _pullback(closes: list[float], last: float, down_days: int) -> bool:
    if last >= closes[-1]:
        return False
    for i in range(1, down_days):
        if closes[-i] >= closes[-(i + 1)]:
            return False
    return True


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)
