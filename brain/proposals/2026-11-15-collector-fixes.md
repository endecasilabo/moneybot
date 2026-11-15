# 2026-11-15 — Arreglar `dev` tras la reestructura por servicios

Estado: aceptada
Rama: `feat/collector-fixes`
PR: https://github.com/frandiegoacosta/moneybot/pull/9

## Problema

El commit `0636179` ("multiple services arquitecture") movió el bot a `services/collector` y dejó
`dev` sin poder desplegarse:

- `infra.yml` no era YAML válido (la descripción `>-` tenía indentación mixta). Deploy e Infra
  fallaban en 0 s en cada push.
- La imagen se construía con `services/collector` como contexto, pero el job lee
  `/app/config/bot.yml` y `dbt/models/base/base_bar.yml`. Ninguno de los dos entraba en la imagen.
- `build-service-image.yml` leía `secrets.GCP_REGION` y `secrets.GCP_ARTIFACT_REGISTRY_NAME`, que no
  existen en el repo. Además solo publicaba el tag `<sha>`, mientras Terraform apunta los jobs a
  `collector:latest`.
- `Bars` pedía `ALPACA_KEY`/`ALPACA_SECRET` al construirse, así que sus tests fallaban sin
  credenciales.
- Se borró `src/strategy.py` (`decide()`) aunque no fue intencional. `src/backtest.py`,
  `src/portfolio.py` y `tests/` quedaron importando módulos que ya no existían, y el CI dejó de
  correrlos.
- Terraform creaba el dataset `moneybot` en `us-central1`, pero los datasets que ya existen
  (`moneybot_dev`, `src`) están en la multirregión US.

Estado de GCP (`moneybot-514003`) al 2026-11-15:

- No hay jobs de Cloud Run ni schedulers, y el audit log no registra ninguno en 30 días.
- Artifact Registry solo tiene `bot:latest`, del 2026-11-07.
- La instancia Cloud SQL `moneybot` está `RUNNABLE` y genera costo sin uso.
- El último deploy de `main` fue el 2026-11-07.

## Alternativas consideradas

1. **Copiar `config/` y el YAML del schema dentro de `services/collector`.** Duplica archivos que
   también usa dbt.
2. **Contexto en la raíz del repo y `Dockerfile.dockerignore` junto al Dockerfile.** Se mantiene una
   sola copia de cada archivo, y BuildKit lee el allowlist específico del Dockerfile. Elegida.
3. **Named build context (`--build-context`).** Obliga a pasar el flag también en cada build local.

Para el backtest, las opciones eran moverlo a `research/` (elegida), borrarlo o dejarlo roto.

## Evidencia

- Validé los workflows con `yaml.safe_load`. El `infra.yml` original falla en la línea 16.
- `services/collector/tests`: 7 tests OK con Python 3.12.
- `research/tests`: 53 tests OK, incluido `test_strategy.py` restaurado.
- No probé el build de la imagen porque no hay Docker en local. Lo valida el primer Deploy.

## Decisión

- La imagen se construye desde la raíz con `services/collector/Dockerfile.dockerignore` como
  allowlist. La imagen base pasa a `python:3.12-slim`, la misma versión que usa el CI.
- `build-service-image.yml` usa `vars.GCP_REGION` (por defecto `us-central1`) y el repositorio
  `moneybot`, y mueve `:latest` a cada imagen construida.
- `Bars` lee las credenciales en `collect()`.
- `decide()`, el backtest y la cartera viven en `research/` (`PYTHONPATH=research`, imports
  `src.*`). El CI los corre junto con `services/*/`. El job de trade **no** se restauró: hoy el bot
  no opera.
- Nueva variable de Terraform `bq_location = "US"`, usada por el dataset y por `BQ_LOCATION`. dbt lee
  `BQ_LOCATION` (por defecto `US`).

## Seguimiento

- [architecture/0004-servicios.md](../architecture/0004-servicios.md).
- Antes de mergear a `main`, tener en cuenta que el apply de `infra` intentará borrar la instancia
  Cloud SQL `moneybot`. Procedimiento:
  [runbooks/2026-11-15-drop-cloudsql.md](../runbooks/2026-11-15-drop-cloudsql.md).
- `.github/cloudbuild.yml` ya no lo usa ningún workflow, porque el build corre en el runner.
  Queda pendiente borrarlo.
