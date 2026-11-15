#!/usr/bin/env bash
# Retira la instancia Cloud SQL `moneybot` antes del primer deploy de BigQuery a main.
# Contexto y resultado: brain/runbooks/2026-11-15-drop-cloudsql.md
#
# Uso, desde la raíz del repo:
#   bash brain/runbooks/2026-11-15-drop-cloudsql.sh            # sin export
#   EXPORT=1 bash brain/runbooks/2026-11-15-drop-cloudsql.sh   # exporta la base a GCS antes de borrar
#   EXPORT=1 CONFIRM=moneybot bash brain/runbooks/2026-11-15-drop-cloudsql.sh   # sin terminal interactiva
#
# Requiere: gcloud autenticado con permisos sobre el proyecto, terraform >= 1.5 en el PATH (infra/terraform.tf).
# Es idempotente: si un paso ya está hecho, lo salta. Deja un log junto a este archivo.

set -euo pipefail

P="${PROJECT_ID:-moneybot-514003}"
INSTANCE=moneybot
BUCKET="${P}-moneybot-tfstate"
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="${HERE}/2026-11-15-drop-cloudsql.log"

exec > >(tee -a "$LOG") 2>&1
echo "== $(date -u +%FT%TZ) proyecto=${P} instancia=${INSTANCE} export=${EXPORT:-0}"

command -v terraform >/dev/null || { echo "falta terraform en el PATH"; exit 1; }
test -d infra || { echo "ejecutar desde la raíz del repo"; exit 1; }

exists=1
gcloud sql instances describe "$INSTANCE" --project "$P" >/dev/null 2>&1 || exists=0

# Se confirma antes de tocar nada: cancelar a mitad dejaría la instancia sin protección y fuera del estado.
if [ "$exists" = 1 ]; then
  # CONFIRM=moneybot sirve cuando no hay terminal interactiva (p. ej. `!` en Claude Code).
  answer="${CONFIRM:-}"
  if [ -z "$answer" ]; then
    read -r -p "Esto borra la instancia Cloud SQL '${INSTANCE}' (irreversible). Escribe '${INSTANCE}' para seguir: " answer \
      || { echo "sin terminal para confirmar: pasa CONFIRM=${INSTANCE}. No se tocó nada"; exit 1; }
  fi
  test "$answer" = "$INSTANCE" || { echo "cancelado, no se tocó nada"; exit 1; }
fi

# 1. Export opcional. La cuenta de servicio de la instancia necesita escribir en el bucket.
if [ "${EXPORT:-0}" = 1 ] && [ "$exists" = 1 ]; then
  sa="$(gcloud sql instances describe "$INSTANCE" --project "$P" --format='value(serviceAccountEmailAddress)')"
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member "serviceAccount:${sa}" --role roles/storage.objectAdmin --quiet >/dev/null
  dest="gs://${BUCKET}/backup/cloudsql-${INSTANCE}-$(date -u +%Y%m%d%H%M%S).sql"
  gcloud sql export sql "$INSTANCE" "$dest" --database=moneybot --project "$P" --quiet
  gcloud storage buckets remove-iam-policy-binding "gs://${BUCKET}" \
    --member "serviceAccount:${sa}" --role roles/storage.objectAdmin --quiet >/dev/null
  echo "export: ${dest}"
fi

# 2. Quitar la protección contra borrado de la API.
if [ "$exists" = 1 ]; then
  gcloud sql instances patch "$INSTANCE" --project "$P" --no-deletion-protection --quiet
fi

# 3. Sacar del estado los recursos que Terraform ya no declara y que no puede destruir.
export TF_VAR_project_id="$P"
terraform -chdir=infra init -input=false -reconfigure \
  -backend-config="bucket=${BUCKET}" -backend-config="prefix=moneybot" >/dev/null
in_state="$(terraform -chdir=infra state list)"
for addr in google_sql_database_instance.main google_sql_database.bot google_sql_user.bot; do
  if grep -qx "$addr" <<<"$in_state"; then
    terraform -chdir=infra state rm "$addr"
  else
    echo "ya no está en el estado: ${addr}"
  fi
done

# 4. Borrar la instancia. Irreversible.
if [ "$exists" = 1 ]; then
  gcloud sql instances delete "$INSTANCE" --project "$P" --quiet
else
  echo "la instancia ${INSTANCE} ya no existe"
fi

echo "== listo. Recursos SQL que quedan en el estado (Terraform los borra en el próximo apply):"
terraform -chdir=infra state list | grep -E 'sql|db_password|random_password|job_db' || echo "(ninguno)"
