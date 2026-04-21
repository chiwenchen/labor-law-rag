#!/usr/bin/env bash
# Restore postgres from an S3 backup.
# Refuses to run unattended — the read prompt returns empty via SSM send-command
# which fails the confirmation check, preventing accidental automation.
#
# Usage:
#   ./restore.sh                                     # latest
#   ./restore.sh backups/pgdump-20260422T190000Z.sql.gz

set -euo pipefail

APP_DIR="/opt/vera-hr"
ENV_FILE="${APP_DIR}/.env"
cd "${APP_DIR}"

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

KEY="${1:-}"
if [[ -z "${KEY}" ]]; then
  KEY="$(aws s3api list-objects-v2 \
    --bucket "${S3_BUCKET}" \
    --prefix "backups/pgdump-" \
    --query 'reverse(sort_by(Contents,&LastModified))[0].Key' \
    --output text \
    --region "${REGION}")"
  echo "[restore] latest backup: ${KEY}"
fi

TMP="/tmp/$(basename "${KEY}")"
trap 'rm -f "${TMP}"' EXIT

aws s3 cp "s3://${S3_BUCKET}/${KEY}" "${TMP}" --region "${REGION}"

echo "[restore] WARNING: this will DROP and recreate data in '${POSTGRES_DB}'"
read -rp "Continue? [y/N] " yn
[[ "${yn}" == "y" || "${yn}" == "Y" ]] || { echo "aborted"; exit 1; }

gunzip -c "${TMP}" | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "[restore] done"
