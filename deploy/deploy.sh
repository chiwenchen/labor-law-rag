#!/usr/bin/env bash
# Runs on the EC2 host via SSM send-command from GitHub Actions.
# Sync configs from S3, render .env from SSM, pull new images, restart stack.

set -euo pipefail

APP_DIR="/opt/vera-hr"
REGION="${AWS_REGION:-ap-northeast-1}"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET must be provided}"

# Sync configs. No --delete: runtime-created files (.env, .bootstrapped, logs)
# live alongside the configs and must be preserved. Renaming a config leaves a
# harmless stale copy; clean up manually if ever needed.
echo "[deploy] sync configs from s3://${S3_BUCKET}/config/"
aws s3 sync "s3://${S3_BUCKET}/config/" "${APP_DIR}/" \
  --region "${REGION}" \
  --exclude ".env*"

chmod +x "${APP_DIR}"/*.sh 2>/dev/null || true

echo "[deploy] re-render .env from SSM"
/usr/local/bin/vera-hr-render-env "${REGION}" "/vera-hr" "${APP_DIR}/.env"

# vera-hr-render-env overwrites .env, so append bucket/region every time for backup.sh.
{
  echo "S3_BUCKET='${S3_BUCKET}'"
  echo "AWS_REGION='${REGION}'"
} >> "${APP_DIR}/.env"

cd "${APP_DIR}"

echo "[deploy] pulling new images"
docker compose -f docker-compose.prod.yml pull

echo "[deploy] restarting stack"
docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo "[deploy] pruning old images"
docker image prune -af --filter "until=168h" || true

echo "[deploy] installing systemd backup timer"
if [[ -f "${APP_DIR}/systemd/vera-hr-backup.service" ]]; then
  sudo install -m 644 "${APP_DIR}/systemd/vera-hr-backup.service" /etc/systemd/system/
  sudo install -m 644 "${APP_DIR}/systemd/vera-hr-backup.timer"   /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now vera-hr-backup.timer
fi

echo "[deploy] status"
docker compose -f docker-compose.prod.yml ps
echo "[deploy] done"
