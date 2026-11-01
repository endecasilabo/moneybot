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

Todo pasa por el Makefile. `make test` corre los tests. `make release` corre los tests y manda el build a Cloud Build. Cloud Build construye `bot:latest`, la sube a Artifact Registry y, si los jobs ya existen, actualiza `moneybot-trade` y `moneybot-snapshot`.

El proyecto GCP ya existe. Región default `us-central1` (Cloud Scheduler tiene que existir en esa región). Cloud SQL `db-f1-micro` queda prendido: no escala a cero. `deletion_protection` está en true. Para borrar la instancia, primero pasalo a false y aplicá de nuevo.

El state de Terraform guarda el password de la base. No lo subas a un repo. Las keys de Alpaca no van al Terraform ni al repo.

```bash
make infra PROJECT_ID=TU_PROYECTO GITHUB_REPOSITORY=owner/moneybot
```

Ese apply crea Artifact Registry, Cloud SQL, Cloud Build, la cuenta de GitHub Actions y los secretos vacíos de Alpaca. No crea los jobs. Si falla porque la cuenta de Cloud Build o el service agent de Scheduler todavía no existen, corré el mismo comando de nuevo.

```bash
export ALPACA_KEY=APCA_API_KEY_ID
export ALPACA_SECRET=APCA_API_SECRET_KEY
make secrets PROJECT_ID=TU_PROYECTO
make release PROJECT_ID=TU_PROYECTO
make jobs PROJECT_ID=TU_PROYECTO
```

`make release` empuja la imagen. `make jobs` crea los dos Cloud Run Jobs y los Scheduler apuntando a `bot:latest`. Las versiones de Alpaca tienen que existir antes de `make jobs`.

En GitHub, el workflow `.github/workflows/ci.yml` corre `make test` en cada push y PR. En `main`, y con `workflow_dispatch`, corre `make deploy`. Hacen falta estos secrets, con los outputs `wif_provider` y `ci_service_account`:

- `WIF_PROVIDER`
- `WIF_SERVICE_ACCOUNT`
- `GCP_PROJECT_ID`

Cambiar `config/bot.yaml` (incluido `trading_enabled: true`) exige otro `make release`.

## Tests

```bash
make test
```
