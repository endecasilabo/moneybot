# APIs de Alpaca que usa moneybot

Referencia de **qué se llama, desde dónde, con qué parámetros y qué devuelve**. SDK: `alpaca-py`
(versión fijada en `app/requirements.txt`). Revisado contra el código el 2026-11-07.

Docs oficiales:
- Trading API: https://docs.alpaca.markets/reference/getaccount-1 (cuenta, órdenes, posiciones, reloj)
- Market Data, barras: https://docs.alpaca.markets/reference/stockbars
- Market Data, último trade: https://docs.alpaca.markets/reference/stocklatesttrades-1
- Modelos de alpaca-py: https://alpaca.markets/sdks/python/api_reference/data/models.html#bar

## Clientes y autenticación

| Cliente (alpaca-py) | Host | Dónde se crea |
|---|---|---|
| `TradingClient(key, secret, paper=False, url_override=LIVE_TRADING_URL)` | `https://api.alpaca.markets` | `src/jobs.py:alpaca_clients` |
| `StockHistoricalDataClient(key, secret)` | `https://data.alpaca.markets` | `src/jobs.py:alpaca_clients`, `src/backtest.py:fetch_history` |

- Credenciales: `ALPACA_KEY` / `ALPACA_SECRET` (cuenta **live**). Se mandan como cabeceras
  `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY`.
- `guard_live` rechaza cualquier `APCA_API_BASE_URL` que contenga `paper`. No existe modo paper.
- Los mismos keys sirven para Trading y para Market Data. El feed SIP depende de la suscripción
  de la cuenta.

## Trading API (`TradingClient`)

| Llamada | Endpoint REST | Usada en | Para qué |
|---|---|---|---|
| `get_clock()` | `GET /v2/clock` | `trade_window` | `timestamp`, `is_open` y `next_close`. Decide si estamos en la ventana de envío (`in_submit_window`) y qué sesión es "hoy". |
| `get_open_position(symbol)` | `GET /v2/positions/{symbol}` | `long_qty` | `qty` actual. Un 404 / `40410000` ("position does not exist") se trata como 0. |
| `get_account()` | `GET /v2/account` | `trade_window` (buy), `take_snapshot` | `cash` (comprobar que llega para `qty × precio`), `equity`, `buying_power`, `portfolio_value`. |
| `submit_order(MarketOrderRequest)` | `POST /v2/orders` | `trade_window` | Orden market `time_in_force=CLS` (se ejecuta en la subasta de cierre). Solo si `trading_enabled: true`. |
| `get_orders(GetOrdersRequest(status=OPEN, limit=100))` | `GET /v2/orders` | `take_snapshot` | Órdenes abiertas, guardadas en `account_snapshots`. |
| `get_all_positions()` | `GET /v2/positions` | `take_snapshot` | Una fila por posición en `position_snapshots`. |

### La orden que se envía

```python
MarketOrderRequest(
    symbol="SPY",
    qty=1,                                   # buy: cfg.qty / sell: toda la posición
    side=OrderSide.BUY,                      # o SELL
    time_in_force=TimeInForce.CLS,           # market-on-close
    client_order_id="scherman-spy-buy-2026-11-06",
)
```

- **Idempotencia**: `client_order_id` es único por símbolo, lado y sesión. Si Alpaca responde con
  un error de `client_order_id` duplicado, se registra como `duplicate` y no se reintenta.
- **CLS**: Alpaca solo acepta órdenes MOC hasta unos minutos antes del cierre (~15:50 NY), y una
  vez enviada no se puede modificar. Por eso existe `submit_before_close_minutes` y el mínimo de
  10 minutos de `in_submit_window`.
- Campos de la respuesta que se guardan (`order_payload` / `upsert_order`): `id`,
  `client_order_id`, `status`, `filled_avg_price`, `symbol`, `side`, `qty`.

## Market Data API (`StockHistoricalDataClient`)

| Llamada | Endpoint REST | Usada en | Parámetros |
|---|---|---|---|
| `get_stock_bars(StockBarsRequest)` | `GET /v2/stocks/bars` | `fetch_bars` (live), `fetch_history` (backtest) | `timeframe=Day`, `feed=SIP`, `adjustment=SPLIT`, `limit=10000`. Live: desde `trend_window × 3` días atrás hasta hoy (excluido). |
| `get_stock_latest_trade(StockLatestTradeRequest)` | `GET /v2/stocks/trades/latest` | `fetch_latest` | `feed=SIP`. Su `price` hace de cierre provisional de hoy. Se rechaza si tiene > 5 min (`STALE_TRADE`). |

### Formato de respuesta

`get_stock_bars` devuelve un `BarSet`. `.data` es `{symbol: [Bar, ...]}` (lo extrae `bars_for`).

| Campo alpaca-py | JSON REST | Significado |
|---|---|---|
| `timestamp` | `t` | **Inicio** de la barra, UTC (RFC-3339). Una barra diaria sale a medianoche NY (04:00/05:00 UTC). |
| `open` | `o` | Precio de la primera operación del intervalo |
| `high` | `h` | Precio máximo |
| `low` | `l` | Precio mínimo |
| `close` | `c` | Precio de la última operación del intervalo |
| `volume` | `v` | Acciones negociadas |
| `trade_count` | `n` | Número de operaciones |
| `vwap` | `vw` | Precio medio ponderado por volumen: Σ(precio·acciones)/Σ(acciones) |

El bot solo usa `timestamp` y `close`.

`get_stock_latest_trade` devuelve `{symbol: Trade}` con `timestamp`, `price`, `size`,
`exchange`, `id`, `conditions` y `tape`. Se usan `price` y `timestamp`.

### Ejemplo real: SPY, barras de 1 hora, 2026-11-06 (SIP)

```
hora NY     open     high      low    close      volume  trades      vwap
04:00     734.63   738.03   730.64   736.30     314,800   8,363   735.193   ← pre-market
09:00     734.89   742.21   732.43   740.57   8,788,362 137,287   737.841   ← incluye la apertura 9:30
15:00     738.04   739.11   735.07   735.34  12,471,379 145,161   736.706   ← última hora regular
16:00     735.37   738.32   735.10   735.95   7,249,057   9,666   735.520   ← after-hours
19:00     736.11   736.53   736.00   736.53      30,725     804   736.218
```

Las barras intradía cubren de **04:00 a 20:00 NY** (pre-market + regular + after-hours). La
sesión regular (9:30–16:00) va de la barra 09:00 a la 15:00, y la de 09:00 mezcla media hora de
pre-market.

### Parámetros que importan

- **`timeframe`**: `1–59Min`, `1–23Hour`, `1Day`, `1Week`, `1/2/3/4/6/12Month`. En alpaca-py:
  `TimeFrame.Day`, `TimeFrame.Hour` o `TimeFrame(15, TimeFrameUnit.Minute)`.
- **`feed`**: `SIP` (tape consolidado de todos los exchanges, el que usa el bot) o `IEX` (un solo
  exchange, ~2–3 % del volumen). Sin suscripción de pago, SIP no deja pedir los últimos ~15 min.
- **`adjustment`**: `RAW`, `SPLIT` (el que usa el bot), `DIVIDEND` o `ALL`. Con `SPLIT` los
  precios **no reflejan dividendos**, y el backtest infravalora buy-and-hold (~1,3 %/año en SPY).
- **Historia**: SIP llega hasta ~2016. `fetch_history` avisa si Alpaca recorta en silencio el
  `start` pedido.
- **Paginación**: `limit` de hasta 10.000 por página, con `next_page_token`. alpaca-py pagina
  solo.

## Lo que Alpaca ofrece y el bot no usa (todavía)

| API | Para qué serviría aquí |
|---|---|
| Quotes (`/v2/stocks/quotes`, bid/ask) | Ver el spread antes de mandar la orden. |
| Snapshot (`/v2/stocks/snapshots`) | Último trade + quote + barra diaria en una sola llamada. Podría sustituir a `fetch_latest`. |
| Trades históricos (`/v2/stocks/trades`) | Microestructura. No aporta a una estrategia diaria. |
| Corporate actions (`/v1/corporate-actions`) | Dividendos y splits, para corregir el backtest. |
| Calendar (`GET /v2/calendar`) | Días de mercado y medias sesiones. Hoy se deduce de `get_clock().next_close`. |
| Streaming (WebSocket) | Datos en tiempo real. Innecesario con un cron diario. |

## Errores que el código trata explícitamente

- `APIError` 404 / `40410000` en `get_open_position`: sin posición, qty = 0.
- `APIError` de `client_order_id` duplicado en `submit_order`: orden ya enviada, run `skipped`.
- Cualquier otro `APIError`: se guarda la orden como `error`, se relanza y `guarded` cierra el
  run con `finish_run(..., "error", ...)`.
