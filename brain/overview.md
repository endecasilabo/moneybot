# Cómo funciona el bot (resumen rápido)

Mental model actual. Si cambia el comportamiento, actualizar esta página en la misma rama (ver
[AGENTS.md §5](../AGENTS.md#5-la-carpeta-brain)).

## Qué hace

**Pendiente al 2026-11-15:** las claves de Alpaca dan 401, así que todo run termina en `error`. Ver
`brain/runbooks/2026-11-15-handoff-alpaca.md`.

**Hoy no opera.** En Cloud Run solo existe el servicio `services/collector`, con dos jobs:
`snapshot` (estado de la cuenta) y `bars` (barras horarias de SPY). El patrón Scherman (`decide()`)
vive en `research/` y solo se usa en el backtest local. Volver a operar requiere un servicio
`trade` (ver `brain/architecture/0004-servicios.md`). Debajo queda descrito cómo operaba, como
referencia para ese servicio.

## La decisión (`research/src/strategy.py:decide`)

Entrada: lista de cierres completados (`closes`), el último precio como proxy del cierre de hoy
(`last`), y si ya hay posición (`in_position`). Pura: no toca red, DB ni reloj.

1. **Tendencia**: SMA de `trend_window` (200) días incluyendo hoy > SMA de 200 de ayer.
2. **Entrada** (si está flat): tendencia ok + 3er día bajista consecutivo (`down_days`) → `buy`.
3. **Salida** (si está long): último precio > SMA de `exit_window` (5) días → `sell`.
4. Cualquier otro caso → `hold`, con una `reason` que explica por qué (`trend_off`,
   `no_pullback`, `in_position`, `insufficient_history`).

Una sola posición, tamaño fijo (`qty`, default 1), sin stop, sin margen, sin fracciones.

## El pipeline (`services/collector/entrypoint.py` → `src/jobs.py`)

```
python entrypoint.py snapshot|bars   # trade: eliminado en 0636179
guarded(job, fn)
  -> load_config()        # config/bot.yml, valida mode=live, feed=sip, etc.
  -> guard_live(cfg)       # aborta si mode != live o si la URL de Alpaca es paper
  -> connect()             # cliente BigQuery; las tablas las crea dbt/, no el bot
  -> start_run() -> fn(conn, run_id, cfg) -> finish_run()
```

Layout tras la reestructura de `dev`: ver `brain/architecture/0002-reestructura-dev.md`.

`fn` es `trade_window` o `take_snapshot`:

- **`trade_window`**: solo actúa si faltan entre 10 y `submit_before_close_minutes` minutos para el
  cierre (`in_submit_window`). Pide cierres completos + el último trade (falla si tiene más de 5
  minutos, `STALE_TRADE`). Llama a `decide()`, guarda la señal (`signals`), y si la acción es
  `buy`/`sell` manda una orden `cls` idempotente (`client_order_id = scherman-{symbol}-{side}-
  {fecha}`) — pero solo si `trading_enabled: true` en `config/bot.yml`.
- **`take_snapshot`**: lee cuenta, posiciones y órdenes abiertas de Alpaca y las guarda. No decide,
  no opera.

## Los datos (BigQuery, dataset `moneybot` en `US`; las tablas las crea Terraform, dbt solo vistas)

Terraform crea las tablas (`infra/main.tf`, `local.tables`). `runs` tiene una fila por ejecución:
`start_run` la inserta y `finish_run` la actualiza con `UPDATE`. `account_snapshots` y
`position_snapshots` las escribe `snapshot`, y `base_bar` la escribe `bars` (columnas en
`dbt/models/base/base_bar.yml`). `signals` y `orders` están creadas para el futuro servicio `trade`,
pero hoy nada escribe en ellas. dbt no construye modelos: los borradores `bars`, `assets` y
`order_intents` están desactivados en `dbt/dbt_project.yml`. El job lee el dataset de `BQ_DATASET`.
Detalle y motivos en `brain/architecture/0003-bigquery.md`. Para pruebas locales:
`BQ_DATASET=moneybot-514003.moneybot_dev` y `dbt build` (target `dev` por defecto).

## Lo que se pide a Alpaca

Solo dos cosas: barras **diarias** (`TimeFrame.Day`, SIP, `Adjustment.SPLIT`, de cada una se usa
solo `close`) y el **último trade** como proxy del cierre de hoy. Alpaca ofrece también barras de
minuto u hora (con pre-market y after-hours), trades, quotes, snapshots y corporate actions, pero
`decide()` no los necesita. Los precios **no incluyen dividendos**. Detalle y ejemplo horario en
`brain/spikes/2026-11-03-sizing-y-cartera.md`.

## Backtesting local (`research/src/backtest.py`)

`PYTHONPATH=research python -m unittest discover -s research/tests`.

No forma parte del pipeline de Cloud Run. Es una herramienta de desarrollo con tres piezas sobre
cualquier estrategia (`Strategy`, cualquier callable con la firma de `decide()`): `simulate`
(replay sobre historia real), `monte_carlo` (replay sobre rutas sintéticas por resampling de
retornos) y `benchmark` (varias estrategias, pasado o futuro, una tabla ordenada por retorno). Ver
`brain/architecture/0001-local-backtesting.md`.

**Importante**: `simulate()` reinvierte el 100% del equity en cada ciclo (compounding completo).
El bot en vivo no hace eso — compra una cantidad fija de acciones (`qty`, default 1) y nunca usa
todo el capital. Los números de retorno del backtest no son comparables 1:1 con lo que haría el
bot real con `qty=1`.

## Cartera multi-activo (`research/src/portfolio.py`)

Tampoco toca Cloud Run ni `src/backtest.py`. `simulate_portfolio()` corre la misma `Strategy`
de forma independiente por símbolo (mismo timing in/out que `simulate()`) y reparte capital entre
los símbolos activos cada día, por `weighting="equal"` (1/N) o `"inverse_vol"` (proporcional a la
inversa de la volatilidad reciente de cada activo). Rebalancea todos los días, no en un calendario
fijo — porque la entrada/salida es por señal, no periódica. No implementa HRP (correlación entre
activos); ver `brain/proposals/2026-11-03-hierarchical-risk-parity.md` para por qué eso quedó
afuera de esta primera versión.

## Lo que hoy es un atajo consciente (buscar `ponytail:` en el código)

- El último trade como proxy del cierre oficial — la subasta puede llenar a otro precio.
- `STALE_TRADE` fijo en 5 minutos en vez de leer el entitlement SIP de la cuenta al arrancar.
