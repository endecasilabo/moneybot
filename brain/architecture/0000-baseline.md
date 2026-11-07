# 0000 — Baseline

Fecha: 2026-11-03. Estado: vigente. Snapshot de la arquitectura actual, punto de partida para
futuras entradas (`NNNN-<slug>.md`) de este directorio.

## Componentes

- **Estrategia** (`src/strategy.py`): función pura `decide()`. Separada del resto a propósito
  — se puede probar y explorar sin tocar Alpaca ni Postgres.
- **Orquestación** (`src/jobs.py`): guardas de seguridad, ventana de envío, llamadas a
  Alpaca, carga de config. Es la única capa con efectos secundarios de negocio.
- **Persistencia** (`src/db.py` + `schema.sql`): Cloud SQL Postgres, esquema aplicado con
  `CREATE TABLE IF NOT EXISTS` al arrancar cada run. Sin migraciones versionadas — el esquema actual
  es aditivo y lo suficientemente simple para no necesitarlas todavía.
- **Config** (`config/bot.yml`): parámetros de estrategia + `trading_enabled`. Vive en el repo, no
  en Secret Manager, porque no es secreto — es el flag de armado y se revisa en PR.
- **Infra** (`infra/main.tf`): dos Cloud Run Jobs + dos Cloud Scheduler, misma imagen. Dos jobs en
  vez de uno porque `trade` y `snapshot` tienen cadencias y objetivos distintos (decidir/operar vs.
  observar), y separarlos evita que un fallo de snapshot bloquee una ventana de trading.
- **CI/CD** (`.github/workflows/`): `ci` corre tests + build en cada push; `ops` es manual
  (infra/secrets/jobs) para no aplicar Terraform en cada push.

## Por qué está así (fundamento)

- **`decide()` pura**: permite explorar variantes de la estrategia (sección 3 de `AGENTS.md`) sin
  credenciales ni riesgo, y hace que `test_strategy.py` no necesite mocks.
- **Guard contra paper** (`guard_live`): la única cuenta disponible para este bot es live; permitir
  paper daría una falsa sensación de "modo seguro" que no existe en el código real, así que se
  bloquea explícitamente en vez de dejarlo como posibilidad silenciosa.
- **`trading_enabled` como único interruptor**: un solo flag, versionado y revisado en PR, en vez de
  credenciales distintas por entorno — más simple de auditar que "¿qué cuenta está configurada hoy?".
- **Idempotencia por `client_order_id`** (`scherman-{symbol}-{side}-{fecha}`): el job de trade puede
  reintentarse (cron cada 5 min dentro de la ventana) sin mandar la orden dos veces.
- **Último trade como proxy del cierre** (`ponytail` en `src/jobs.py`): el cierre oficial no existe
  todavía cuando el job decide; es un atajo documentado, no un bug.

## Qué no está resuelto todavía

Ver comentarios `ponytail:` en `src/jobs.py` para los atajos conocidos y su upgrade path. No
hay backtesting automatizado del patrón ni comparación histórica de variantes — hoy se razona sobre
`decide()` directamente (ver `AGENTS.md §3`).
