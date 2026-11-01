# moneybot

Bot de Alpaca que opera **SPY en live** con el patrón publicado de Iván Scherman, y un job aparte que solo guarda el estado de la cuenta.

El 491% de 2023 es el World Cup de futuros. Esos modelos no están publicados. Este repo implementa el patrón de la [entrevista de Business Insider](https://www.businessinsider.com/stock-trading-strategy-quant-fund-manager-competition-champion-sp500-return-2024-9): Scherman dice que su fondo no lo opera, y que la réplica cercana es el ETF SPY. La ejecución es la opción 1 de esa nota: market-on-close.

## Reglas

- Tendencia: la SMA de 200 de hoy (el último trade cuenta como cierre) es mayor que la SMA de 200 de ayer.
- Entrada: hoy es el tercer día bajista. Los dos cierres anteriores ya bajaron, y el último precio está debajo del cierre de ayer. Orden `cls` de `qty` acciones.
- Salida: hay posición long, y el último precio está arriba de la SMA de 5. Orden `cls` de toda la posición.
- Sin stop. El tamaño es fijo (`qty`, default 1). Si el cash no cubre `qty * último precio`, no compra. No usa margen. No fracciona: Alpaca rechaza fracciones con `cls`.
- Una posición. Si ya está long, no compra. Si está flat, no vende.
- Idempotencia: `client_order_id = scherman-spy-{buy|sell}-{fecha}`.

El cierre oficial todavía no existe cuando el job decide. Usa el último trade como proxy. La subasta puede llenar a otro precio. Hace falta SIP en tiempo real. Si el último trade tiene más de 5 minutos, el job falla y no manda la orden. Si la cuenta no tiene SIP, falla y no opera con cierres IEX.

`trading_enabled` nace en `false`. Con `false` guarda la señal y no manda la orden. Pasa a `true` en `config/bot.yaml`, reconstruí la imagen y volvé a desplegar el job.

`mode` distinto de `live`, o `APCA_API_BASE_URL` con `paper`, aborta el proceso.

## Dos ejecuciones

Misma imagen, dos Cloud Run Jobs, dos Cloud Scheduler en `America/New_York`.

| Job | Cron default | Qué hace |
| --- | --- | --- |
| `moneybot-trade` | `*/5 12-16 * * 1-5` | Manda la orden solo si faltan más de 10 min y como máximo 20 min para `next_close`. Cubre el cierre de las 16:00 ET y el cierre temprano de las 13:00 ET. Fuera de esa ventana no toca órdenes. |
| `moneybot-snapshot` | `*/15 9-16 * * 1-5` | Lee cuenta, posiciones y órdenes abiertas. No decide y no opera. |

Los cron son variables de Terraform. Si el job de trade no corre dentro de la ventana, esa sesión no se opera.

## Datos

Cloud SQL Postgres. El proceso aplica `schema.sql` al arrancar (`CREATE TABLE IF NOT EXISTS`).

- `runs`: cada ejecución.
- `signals`: precio, las dos SMA de 200, la SMA de 5, flags, acción y motivo.
- `orders`: órdenes `cls` enviadas.
- `account_snapshots`: equity, cash, buying power y órdenes abiertas.
- `position_snapshots`: posiciones.

## Deploy

No se corre nada en la máquina local. Todo es un workflow de GitHub.

El proyecto GCP ya existe. Región default `us-central1` (Cloud Scheduler tiene que existir ahí). Cloud SQL `db-f1-micro` queda prendido: no escala a cero. `deletion_protection` está en true.

En la consola de GCP, creá una service account con rol Owner y bajá el JSON. En el repo, Settings, Secrets and variables, Actions, cargá:

- `GCP_SA_KEY`: el JSON entero
- `GCP_PROJECT_ID`
- `ALPACA_KEY`
- `ALPACA_SECRET`

La región es la variable `GCP_REGION`. Si no está, los workflows usan `us-central1`.

El state de Terraform vive en el bucket `PROJECT_ID-moneybot-tfstate`. El password de la base queda en ese state, no en el repo. Las keys de Alpaca quedan en GitHub Secrets y en Secret Manager.

Orden, desde Actions, Run workflow:

1. `ops`, acción `infra`. Crea Artifact Registry, Cloud SQL, Cloud Build y los secretos vacíos. No crea los jobs. Si falla porque la cuenta de Cloud Build o el service agent de Scheduler todavía no existen, corré `infra` de nuevo.
2. `ops`, acción `secrets`. Carga las keys de Alpaca en Secret Manager.
3. Un push a `main` corre `ci`: tests y Cloud Build. Cloud Build publica `bot:latest` y, si los jobs ya existen, los actualiza.
4. `ops`, acción `jobs`. Crea `moneybot-trade`, `moneybot-snapshot` y los dos Scheduler apuntando a esa imagen.

Cada push y cada PR corre los tests. Cada push a `main` vuelve a publicar la imagen. Cambiar `config/bot.yaml` (incluido `trading_enabled: true`) es un push a `main`.
