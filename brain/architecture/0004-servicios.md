# 0004 — Un directorio por servicio, investigación aparte

Fecha: 2026-11-15 · Propuesta: [2026-11-15-collector-fixes](../proposals/2026-11-15-collector-fixes.md) ·
Rama: `feat/collector-fixes` (sobre el commit `0636179`)

## Antes / después

| | Antes (0003) | Ahora |
|---|---|---|
| Código desplegable | `app/` + `src/` (una imagen) | `services/<svc>/` (entrypoint, `src/`, tests y Dockerfile propios) |
| Jobs | `trade`, `snapshot` | `snapshot`, `bars`. No hay trade |
| Estrategia y backtest | `src/strategy.py`, `src/backtest.py`, `src/portfolio.py` | `research/src/`, solo local, sin imagen |
| Contexto de build | raíz | raíz, con allowlist en `services/<svc>/Dockerfile.dockerignore` |
| Tablas | dbt (`table_if_absent`) | Terraform (`google_bigquery_table.bot`). dbt solo crea vistas y modelos |
| Ubicación BigQuery | `us-central1` | `US` (`var.bq_location`), igual que `moneybot_dev` y `src` |

## Por qué

- Cada servicio se construye y se cachea por separado: la imagen base (`bedrock`) solo se
  reconstruye cuando cambian las dependencias.
- `research/` no se despliega. Separarlo deja claro que el backtest no corre en Cloud Run.
- BigQuery no permite queries entre ubicaciones distintas, así que todos los datasets van en `US`.

## Deploy y jobs

- El apply de `infra` que corre en cada Deploy usa `image=collector:latest` cuando esa imagen existe.
  Con `image` vacío, Terraform destruiría los jobs y los schedulers.
- Un job de Cloud Run fija el digest de la imagen al crearse o actualizarse. Después de cada build,
  `build-service-image.yml` actualiza los jobs del servicio al tag `<sha>`, y el siguiente apply los
  vuelve a dejar en `:latest`, que apunta al mismo digest.
- El timeout se configura por job en `local.jobs`: `snapshot` 300 s, `bars` 1800 s (para el backfill).

## Pendiente

- Volver a operar requiere un servicio `trade` que importe `decide()`. Hoy `decide()` vive en
  `research/src/strategy.py` y no hay un paquete compartido entre servicios.
