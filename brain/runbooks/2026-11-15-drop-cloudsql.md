# 2026-11-15 — Retirar la instancia Cloud SQL `moneybot`

Estado: ejecutado el 2026-11-15
Script: [2026-11-15-drop-cloudsql.sh](2026-11-15-drop-cloudsql.sh) · Log: `2026-11-15-drop-cloudsql.log`
(se crea al ejecutar) · Propuesta: [2026-11-15-collector-fixes](../proposals/2026-11-15-collector-fixes.md)

## Por qué

Con la migración a BigQuery ([architecture/0003](../architecture/0003-bigquery.md)), `infra/main.tf`
ya no declara la instancia, pero el estado de Terraform (`gs://moneybot-514003-moneybot-tfstate`,
prefijo `moneybot`) todavía la tiene. En el primer apply de `infra` en `main`, Terraform intentaría
destruirla, y la instancia tiene `deletion_protection` activada tanto en Terraform como en la API.
El apply fallaría y bloquearía el deploy.

Estado antes de ejecutar (2026-11-15):

- La instancia `moneybot` (Postgres 16, `db-f1-micro`, `us-central1-c`) está `RUNNABLE` y genera
  costo.
- No tiene backups. Tiene las bases `postgres` y `moneybot`.
- Ningún job escribió nunca en ella: nunca existieron jobs de Cloud Run en el proyecto, según el
  audit log de 30 días. Por eso se espera que esté vacía.

## Qué hace el script

1. Pide escribir `moneybot` **antes de tocar nada**. Si se cancela, no cambia nada.
2. Con `EXPORT=1`, exporta la base `moneybot` a
   `gs://moneybot-514003-moneybot-tfstate/backup/cloudsql-moneybot-<UTC>.sql`. Para eso da
   permiso de escritura temporal a la cuenta de servicio de la instancia y se lo quita al terminar.
3. Quita la protección contra borrado de la API (`--no-deletion-protection`).
4. Ejecuta `terraform state rm` de `google_sql_database_instance.main`, `google_sql_database.bot` y
   `google_sql_user.bot`.
5. Borra la instancia.

Es idempotente: si un paso ya está hecho, lo salta. Toda la salida queda en el `.log`.

**No toca** el secret `moneybot-db-password`, `random_password.db` ni los permisos
`job_sql`/`job_db`. No tienen protección, así que Terraform los destruye en el apply de `infra`
al mergear `dev → main`.

## Cómo ejecutarlo

```bash
# desde la raíz del repo, con gcloud autenticado y terraform en el PATH
bash brain/runbooks/2026-11-15-drop-cloudsql.sh
# o, para guardar antes una copia de la base:
EXPORT=1 bash brain/runbooks/2026-11-15-drop-cloudsql.sh
# sin terminal interactiva (p. ej. `!` en Claude Code), todo en UNA línea:
EXPORT=1 CONFIRM=moneybot bash brain/runbooks/2026-11-15-drop-cloudsql.sh
```

Las variables van en la misma línea que `bash`. Un primer intento del 2026-11-15T10:09Z las puso
en una línea aparte y se ejecutó con `export=0`. El `read` no tenía terminal y el script terminó
sin cambiar nada (primera línea del `.log`).

Para comprobarlo después:

```bash
gcloud sql instances list --project moneybot-514003   # sin moneybot
```

## Resultado

Ejecutado el 2026-11-15T10:12Z con `EXPORT=1 CONFIRM=moneybot`, con la cuenta personal de gcloud.
Exit code 0. Log completo en `2026-11-15-drop-cloudsql.log`.

- **Export:** `gs://moneybot-514003-moneybot-tfstate/backup/cloudsql-moneybot-20261115101243.sql`
  (756 bytes). Solo trae cabeceras y un `GRANT` sobre `public`, sin tablas ni filas: la base
  estaba vacía, como se esperaba.
- El permiso temporal de la cuenta de servicio de Cloud SQL sobre el bucket se quitó.
- Salieron del estado `google_sql_database_instance.main`, `google_sql_database.bot` y
  `google_sql_user.bot`.
- `gcloud sql instances list` ya no devuelve ninguna instancia.

Quedan en el estado y Terraform los destruye en el próximo apply de `infra`: el rol
`roles/cloudsql.admin` del deployer, `job_sql`, `job_db`, el secret `db_password` con su versión,
`random_password.db` y la entrada de `sqladmin.googleapis.com`. Como esa entrada tiene
`disable_on_destroy = false`, la API queda habilitada; solo sale del estado.
