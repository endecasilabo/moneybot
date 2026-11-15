# 0003 — Persistencia en BigQuery

Fecha: 2026-11-11 · Propuesta: [2026-11-11-bigquery](../proposals/2026-11-11-bigquery.md) ·
Rama: `feat/bigquery`

## Antes / después

| | Antes (0002) | Ahora |
|---|---|---|
| Almacén | Cloud SQL Postgres (`db-f1-micro`, siempre encendido) | BigQuery, dataset `moneybot` (US) |
| Conexión desde el job | Socket `/cloudsql` + usuario/contraseña (Secret Manager) | `google-cloud-bigquery` con la cuenta del job (ADC), sin secretos |
| Cliente Python | `psycopg` | `google-cloud-bigquery` |
| Esquema | dbt `dbt-postgres`, `create table if not exists` | dbt `dbt-bigquery`, la misma materialización `table_if_absent` |
| Escritura | `INSERT` / `UPDATE` / `ON CONFLICT` | Solo añadir (`insert_rows_json`); el estado actual sale de vistas `*_latest` |
| Ids | `bigserial` | UUID generados en Python |
| Config del job | `INSTANCE_CONNECTION_NAME`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | `BQ_DATASET` (`<project>.<dataset>`) |
| CI `schema` | Cloud SQL Auth Proxy + contraseña | `dbt build` directo con la cuenta de GitHub Actions |

## Por qué "solo añadir"

BigQuery no aplica claves únicas, los `UPDATE` tardan segundos, dos simultáneos sobre la misma
tabla pueden fallar, y las filas recién insertadas por streaming no admiten DML durante un rato.
Escribir siempre filas nuevas evita los tres problemas. Para "cuál es el estado actual" están las
vistas, que toman el último evento por clave con `QUALIFY ROW_NUMBER() ...`.

La idempotencia de las órdenes no depende de la base de datos: el `client_order_id` determinista
hace que Alpaca rechace la segunda orden del día, y ese rechazo ya se trata como `duplicate`.
`sent_order()` es solo una comprobación previa para ahorrarse esa llamada.

## IAM

- `moneybot-job`: `roles/bigquery.dataEditor` y `roles/bigquery.user` (incluye crear jobs). Creados
  a mano el 2026-11-11 y declarados en Terraform.
- `moneybot-sa` (deployer de GitHub Actions): `roles/bigquery.admin`. Creado a mano y declarado.

## Coste

Con unas pocas filas al día, todo entra en el free tier: 10 GB de almacenamiento y 1 TB de consultas
al mes. El streaming insert se cobra por volumen (~0,01 $ / 200 MB), que aquí es despreciable.
Desaparece el coste fijo de la instancia Cloud SQL cuando se retire (PR posterior).

## Qué queda igual

`decide()`, la ventana de envío, `guard_live`, `trading_enabled`, los crons y los dos jobs actuales
(`trade`, `snapshot`). Esta entrada solo cambia dónde y cómo se guardan los datos.
