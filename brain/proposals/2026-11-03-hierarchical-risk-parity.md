# 2026-11-03 — Hierarchical Risk Parity (HRP) como estrategia futura

Estado: en análisis
Rama: ninguna todavía — propuesta sin código, ver "Seguimiento"
PR: —

Fuente: López de Prado, M. (2016). *Building Diversified Portfolios that Outperform
Out-of-Sample*. [brain/proposals/ssrn-2708678.pdf](ssrn-2708678.pdf), SSRN 2708678.

## Problema

`moneybot` opera un solo símbolo (SPY) con una señal binaria long/flat (`decide()`). Todo el
riesgo está concentrado en una apuesta direccional sobre un único instrumento; no hay
diversificación entre activos. La pregunta que motiva leer este paper: ¿HRP da una estrategia
genuinamente distinta que valga la pena probar, más allá de otra parametrización de `decide()`?

## Resumen del paper

HRP ataca un problema distinto al de `decide()`: no decide *cuándo* operar un activo, decide
*cuánto peso* darle a cada activo de una cartera de N instrumentos, usando la matriz de
correlación. Reemplaza la optimización cuadrática de Markowitz (CLA) — que requiere invertir la
matriz de covarianza y es inestable cuando los activos están muy correlacionados ("la maldición de
Markowitz": a mayor correlación, mayor necesidad de diversificar, pero mayor inestabilidad de la
solución) — por tres pasos basados en clustering jerárquico:

1. **Tree clustering**: arma un árbol de los activos por distancia de correlación
   (`d = sqrt(0.5·(1-ρ))`), con `scipy.cluster.hierarchy.linkage`.
2. **Quasi-diagonalización**: reordena la matriz de covarianza según ese árbol, para que activos
   parecidos queden juntos.
3. **Bisección recursiva**: reparte el peso de arriba hacia abajo entre las dos mitades de cada
   cluster, en proporción inversa a su varianza agregada.

No necesita invertir la matriz de covarianza — funciona incluso si es singular, algo imposible
para un optimizador cuadrático. En el Monte Carlo del paper (10 series de retornos gaussianos
correlacionados, rebalanceo mensual, 10.000 corridas), HRP tuvo 72.47% menos varianza
out-of-sample que CLA (mínima varianza) y 38.24% menos que risk parity tradicional (IVP) —
a pesar de que CLA está optimizado *específicamente* para minimizar varianza in-sample.

## Por qué no encaja en el `Strategy` de `src/backtest.py` tal cual

`Strategy = Callable[[closes: list[float], last: float, in_position: bool], Decision]` — una
serie de precios de un solo activo, una decisión binaria. HRP necesita una matriz TxN de retornos
de **varios** activos y devuelve un vector de pesos continuos, no un `buy`/`sell`/`hold`. No es
"otra estrategia que se puede enchufar" al `simulate()`/`benchmark()` que ya existe — es una capa
distinta (asignación de cartera) que además necesitaría:

- Datos históricos de un universo de activos, no de uno solo (`fetch_history` ya sirve para traer
  cada serie, pero habría que traer varias y alinear fechas).
- Una cadencia de rebalanceo (el paper usa mensual) y un motor de simulación que lleve pesos
  continuos por activo, no una sola posición long/flat.
- Probablemente un módulo nuevo (`src/portfolio.py`), no una función más en `strategy.py`.

## Alternativas consideradas

1. **Forzar HRP dentro de `Strategy`** — descartado: la firma no tiene sentido para N activos y
   pesos continuos; se perdería lo que hace útil al tipo actual (simple, sin ambigüedad).
2. **HRP como motor de simulación aparte, sobre un universo de ETFs correlacionados con SPY**
   (ej. SPY + otros sector ETFs) — la opción que tiene sentido si esto avanza. Reutilizaría
   `fetch_history` por símbolo, pero necesita un `simulate_portfolio()` nuevo.
3. **No hacer nada por ahora** — moneybot está diseñado y operado como una apuesta de un solo
   activo; meter HRP es ampliar el alcance del bot, no optimizar lo que ya existe. Es la opción
   por defecto hasta que se decida lo contrario.

## Evidencia

Solo lectura del paper — **no corrí nada contra datos de `moneybot` todavía**. El resultado citado
(72.47%/38.24% menos varianza) es del Monte Carlo sintético de los autores (retornos gaussianos
simulados), no una prueba con SPY ni con ningún activo real.

## Decisión

Ninguna todavía. Queda como **feature a futuro**: vale la pena probar si moneybot alguna vez deja
de ser "un bot de un solo símbolo" y pasa a operar una cesta de activos — ahí HRP es una forma
robusta de repartir pesos sin optimización cuadrática inestable. Mientras el alcance siga siendo
SPY solo, no hay nada que asignar entre activos y la pregunta no aplica.

## Seguimiento

Si se retoma: abrir `exp/hrp-portfolio-allocation`, definir el universo de activos a probar,
escribir `simulate_portfolio()` (motor de rebalanceo con pesos HRP) como función separada —
reusando `fetch_history()` para los datos pero sin tocar `Strategy`/`simulate()` de
`src/backtest.py`, que deben seguir sirviendo al caso de un solo activo tal como están hoy.
