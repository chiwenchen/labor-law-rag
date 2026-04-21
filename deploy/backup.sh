#!/usr/bin/env bash
# Daily pg_dump → S3. Triggered by systemd timer (see deploy/systemd/).
# Retention (7 days) is enforced by S3 lifecycle rule on the backups/ prefix.
#
# Only the variables needed for the dump are read from .env — avoids exporting
# other secrets (ANTHROPIC_API_KEY etc.) into this process's environment.

set -euo pipefail

APP_DIR="/opt/vera-hr"
ENV_FILE="${APP_DIR}/.env"
cd "${APP_DIR}"

# Extract a single-quoted value from the shell-format .env file.
env_val() {
  # shellcheck disable=SC2016
  sed -n "s/^$1='\\(.*\\)'\$/\\1/p" "${ENV_FILE}" | head -1
}

POSTGRES_USER="$(env_val POSTGRES_USER)"
POSTGRES_DB="$(env_val POSTGRES_DB)"
S3_BUCKET="$(env_val S3_BUCKET)"
REGION="$(env_val AWS_REGION)"
REGION="${REGION:-ap-northeast-1}"

: "${POSTGRES_USER:?POSTGRES_USER not in .env}"
: "${POSTGRES_DB:?POSTGRES_DB not in .env}"
: "${S3_BUCKET:?S3_BUCKET not in .env}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="/tmp/pgdump-${TIMESTAMP}.sql.gz"
S3_KEY="backups/pgdump-${TIMESTAMP}.sql.gz"

trap 'rm -f "${DUMP_FILE}"' EXIT

echo "[backup] dumping postgres..."
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists \
  | gzip -9 > "${DUMP_FILE}"

SIZE="$(stat -c %s "${DUMP_FILE}")"
echo "[backup] dump size: ${SIZE} bytes"

echo "[backup] uploading to s3://${S3_BUCKET}/${S3_KEY}"
aws s3 cp "${DUMP_FILE}" "s3://${S3_BUCKET}/${S3_KEY}" \
  --region "${REGION}" \
  --storage-class STANDARD_IA

echo "[backup] done"
