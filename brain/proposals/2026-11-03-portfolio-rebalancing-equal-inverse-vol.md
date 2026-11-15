# 2026-11-03 — Rebalanceo de cartera: equal-weight e inverse-volatility

Estado: aceptada
Rama: `exp/portfolio-rebalancing`
PR: —

Continúa [2026-11-03-hierarchical-risk-parity.md](2026-11-03-hierarchical-risk-parity.md): ese
análisis identificó que combinar Scherman (timing in/out por activo) con HRP (sizing entre
activos) es conceptualmente válido, pero HRP recalcula una matriz de correlación sobre un
conjunto de activos que cambia día a día según qué dispare Scherman — complejo de integrar bien.

## Problema

Si Scherman decide *cuándo* cada activo de una cesta está long/flat, falta decidir *cuánto* peso
de capital darle a cada uno de los que están activos en un momento dado. HRP es una opción, pero
pesada para un conjunto activo que cambia constantemente. ¿Hay algo más simple que siga siendo
razonable?

## Alternativas consideradas

1. **Equal-weight**: cada activo activo recibe `1/N` del capital, N = cantidad de activos
   actualmente long. Cero datos extra más allá de saber quién está activo. Con N=1 es exactamente
   lo que hace el bot de un solo símbolo hoy — generaliza el caso actual sin romperlo.
2. **Inverse-volatility**: cada activo activo recibe peso proporcional a `1/su volatilidad
   reciente` (ventana móvil de retornos diarios), normalizado para sumar 1. Más riesgo-consciente
   que equal-weight (un activo el doble de volátil recibe la mitad de peso), pero sigue sin
   necesitar la matriz de correlación completa — solo la volatilidad propia de cada activo, que
   se recalcula trivialmente aunque el conjunto activo cambie de un día a otro.
3. **HRP** (ver proposal anterior) — descartada *por ahora* para esta iteración: correlación entre
   activos sobre un conjunto que cambia día a día es la pieza más difícil de las tres y no aporta
   nada hasta tener equal-weight/inverse-vol funcionando como base de comparación.

## Decisión

Implementar **ambas** (1) y (2) como motor de simulación nuevo, separado del motor de un solo
activo. Compararlas entre sí (y contra un solo activo) es la forma de decidir después si vale la
pena el salto a HRP.

## Seguimiento

`src/portfolio.py` (nuevo módulo, no toca `src/backtest.py`):

- `simulate_portfolio(closes: dict[symbol, list[float]], strategy: Strategy, weighting: "equal" |
  "inverse_vol") -> PortfolioResult`. Scherman decide in/out por símbolo cada día (mismo
  `Strategy` que ya existe); al cierre de cada día se recalculan los pesos del día siguiente entre
  los símbolos activos, según `weighting`.
- Rebalanceo: no es periódico (no hay "cada 22 días" como en el paper de HRP) — se recalcula cada
  vez que el conjunto de activos activos puede haber cambiado, es decir, todos los días después de
  evaluar las señales. Es la cadencia más natural dado que Scherman entra/sale por señal, no por
  calendario.
- Tests: con series sintéticas, igual que `tests/test_backtest.py`.

## Resultados

Ver [spikes/2026-11-03-sizing-y-cartera.md](../spikes/2026-11-03-sizing-y-cartera.md) (Idea 3):
equal e inverse-vol acaban casi iguales (~×1,8) con una cesta correlacionada.
