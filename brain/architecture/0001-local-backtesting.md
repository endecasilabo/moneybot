# 0001 — Backtesting, Monte Carlo y benchmarking local

Fecha: 2026-11-03. Estado: vigente. Rama: `feat/backtest-framework`.

## Qué se añadió

`src/backtest.py`, separado del pipeline de Cloud Run (`src/jobs.py` no lo importa, y
`__main__.py` no gana un comando nuevo — se corre aparte con `python -m moneybot.backtest`).

- `Strategy = Callable[[closes, last, in_position], Decision]`: cualquier función con esa firma
  — `decide()` fijado con `functools.partial` para una parametrización, o un algoritmo distinto.
- `simulate(closes, strategy) -> BacktestResult`: replay día por día de `strategy` sobre una lista
  de cierres históricos. Trades, equity curve, retorno final, win rate, max drawdown. No conoce
  `trend_window` ni ningún parámetro de `decide()` — si la estrategia no tiene suficiente historia
  todavía, es su propio `decide()` el que responde `hold`/`insufficient_history`.
- `monte_carlo(closes, strategy, trials, seed) -> list[float]`: resamplea los retornos diarios
  (i.i.d., con reemplazo) para generar rutas de precio sintéticas y corre `simulate` sobre cada
  una. Es un stress test de la estrategia contra la volatilidad histórica reordenada, no un
  modelo de SPY.
- `benchmark(closes, strategies: dict[str, Strategy]) -> list[(nombre, BacktestResult)]`: corre
  `simulate` para cada estrategia nombrada y las ordena por retorno.
- `fetch_history(symbol, start, end)`: trae cierres diarios de Alpaca (solo lectura, reusa
  `bars_for` de `src/jobs.py`), para correr lo anterior con datos reales en local.

## Por qué así (fundamento)

- **Reusa `decide()` sin tocarlo**: la pureza de la función (ver `0000-baseline.md`) es justo lo
  que hace posible este módulo sin mocks ni entorno live.
- **Estrategia = callable, no una tupla de parámetros** (actualizado 2026-11-03): la primera
  versión solo aceptaba `(trend_window, exit_window, down_days)` para `decide()`; se generalizó a
  `Strategy` porque el usuario quiere comparar *distintas* estrategias (no solo distintas
  parametrizaciones de la misma) en pasado (`benchmark`) y futuro (`monte_carlo`). `simulate` ya
  no sabe nada de ventanas — delega por completo en la estrategia, que decide sola si tiene
  suficiente historia.
- **Monte Carlo por resampling i.i.d., no block-bootstrap**: más simple, suficiente para una
  primera estimación de sensibilidad. Si hace falta preservar autocorrelación/clustering de
  volatilidad, ese es el upgrade (ver atajo abajo).
- **Separado de `src/jobs.py`**: cero riesgo de que esta herramienta de desarrollo toque el
  entrypoint que corre en Cloud Run.

## Atajos conscientes

- `monte_carlo` resamplea retornos i.i.d.; no preserva autocorrelación ni volatility clustering.
  shortcut: subestima/sobreestima colas según el régimen, upgrade a block-bootstrap si los
  percentiles se usan para una decisión real de sizing/riesgo.
- `fetch_history` no cachea: cada corrida vuelve a pedir el rango completo a Alpaca.
