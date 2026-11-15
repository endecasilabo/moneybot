# 2026-11-15 — Traspaso: dejar el collector funcionando con claves de Alpaca válidas

Estado: pendiente. Lo hace quien tenga acceso a la cuenta **live** de Alpaca.
Contexto: [proposals/2026-11-15-collector-fixes](../proposals/2026-11-15-collector-fixes.md) ·
[architecture/0004-servicios](../architecture/0004-servicios.md) ·
[runbooks/2026-11-15-drop-cloudsql](2026-11-15-drop-cloudsql.md)

## Dónde quedó (2026-11-15)

En GCP (`moneybot-514003`, región `us-central1`) todo está desplegado desde `main`:

| Recurso | Estado |
| --- | --- |
| Cloud Run jobs `moneybot-snapshot`, `moneybot-bars` | Creados, con imagen `collector:latest` |
| Cloud Scheduler | `snapshot` `*/15 9-16 * * 1-5` y `bars` `35 10-16 * * 1-5`, ambos en `America/New_York` y **activos** |
| BigQuery `moneybot` (US) | `runs`, `signals`, `orders`, `account_snapshots`, `position_snapshots`, `base_bar` |
| Secret Manager | `moneybot-alpaca-key` y `moneybot-alpaca-secret`, versión 1 |
| Cloud SQL | Eliminado |

**Lo único que falla son las claves de Alpaca.** La versión 1 de los secrets salió de los secrets de
GitHub `ALPACA_KEY` y `ALPACA_SECRET`. La clave tiene prefijo `AK` (live) y no lleva espacios,
pero `GET /v2/account` devuelve **401 tanto en live como en paper**. El par está revocado o es
incorrecto.

Mientras no se arregle, cada ejecución programada deja en `moneybot.runs` una fila
`status=error`, `detail={"message": "unauthorized."}`. La primera fue la prueba manual
`b925d29c-…` del 2026-11-15 10:35 UTC. No se envía ninguna orden porque no hay servicio de trade.

## Qué hacer

1. En el dashboard de Alpaca, cuenta **live**, regenerar el par de API keys.
2. Actualizar los secrets de GitHub. Los comandos piden el valor por stdin, sin eco:
   ```bash
   gh secret set ALPACA_KEY
   gh secret set ALPACA_SECRET
   ```
3. Copiarlos a Secret Manager como versión nueva:
   ```bash
   gh workflow run infra.yml --ref main -f action=secrets
   ```
   Los jobs leen `latest` en cada ejecución, así que no hace falta redeployar.
4. Probar:
   ```bash
   gcloud run jobs execute moneybot-snapshot --region us-central1 --project moneybot-514003 --wait
   bq query --use_legacy_sql=false --project_id moneybot-514003 \
     'select job, status, detail, started_at from moneybot.runs order by started_at desc limit 5'
   ```
   Se espera `status=ok` y `detail=positions=<n>`, y una fila nueva en `account_snapshots`.
5. Opcional: lanzar `bars` a mano para hacer el backfill fuera del horario de mercado. El primer run
   descarga las barras horarias de SPY desde 2016-01-01. El timeout de `bars` es de 1800 s.
   ```bash
   gcloud run jobs execute moneybot-bars --region us-central1 --project moneybot-514003 --wait
   ```
6. Opcional: deshabilitar las versiones viejas de los secrets:
   ```bash
   gcloud secrets versions disable 1 --secret moneybot-alpaca-key --project moneybot-514003
   gcloud secrets versions disable 1 --secret moneybot-alpaca-secret --project moneybot-514003
   ```
7. Completar abajo la sección **Resultado** y cambiar el estado a "hecho".

## Si algo falla

- Logs de un job:
  `gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="moneybot-snapshot"' --project moneybot-514003 --freshness 1h --limit 20`
- Si sigue dando 401, revisar que las claves sean de la cuenta live y no de paper. Las de paper
  empiezan por `PK` y contra el endpoint live siempre dan 401.
- `bars` necesita una suscripción con datos **SIP**. Sin ella, Alpaca responde 403 sobre las barras.

## Resultado

_Completar: fecha, quién lo hizo, `run_id` de la primera ejecución `ok` y cuántas barras trajo el
backfill._
