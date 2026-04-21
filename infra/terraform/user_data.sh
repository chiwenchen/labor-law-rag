#!/bin/bash
# Amazon Linux 2023 bootstrap — runs once on first boot.
# Note: `set -x` is intentionally NOT enabled to avoid tracing secret material
# into /var/log/user-data.log. Use explicit `echo` logging instead.
set -euo pipefail

exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

REGION="${region}"
SSM_PREFIX="${ssm_prefix}"
S3_BUCKET="${s3_bucket}"
PROJECT="${project}"
APP_DIR="/opt/$${PROJECT}"
COMPOSE_VERSION="v2.29.7"

echo "[user-data] starting bootstrap"

# --- 2GB swap (bge-m3 uses ~2GB RAM; gives OOM buffer) ---
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "[user-data] swap enabled"
fi

# --- Packages ---
dnf install -y docker git cronie jq amazon-ssm-agent
systemctl enable --now amazon-ssm-agent
systemctl enable --now docker
systemctl enable --now crond
usermod -aG docker ec2-user

# --- Docker Compose v2 plugin (ARM64, pinned version) ---
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL \
  "https://github.com/docker/compose/releases/download/$${COMPOSE_VERSION}/docker-compose-linux-aarch64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# --- Automatic security updates ---
dnf install -y dnf-automatic
sed -i 's/apply_updates = no/apply_updates = yes/' /etc/dnf/automatic.conf
sed -i 's/upgrade_type = default/upgrade_type = security/' /etc/dnf/automatic.conf
systemctl enable --now dnf-automatic.timer

# --- App directory ---
mkdir -p "$${APP_DIR}"
chown ec2-user:ec2-user "$${APP_DIR}"

# --- Helper: render .env from SSM Parameter Store ---
# Writes a shell-safe .env with single-quoted values so POSTGRES_PASSWORD et al.
# survive any special chars. Called by user_data here, and again by deploy.sh on
# each rollout to pick up rotated secrets.
cat > /usr/local/bin/vera-hr-render-env <<'RENDER'
#!/bin/bash
set -euo pipefail
REGION="$1"
PREFIX="$2"
OUT="$3"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

# Fetch all params under the prefix into tab-separated (name, value) pairs.
aws ssm get-parameters-by-path \
  --path "$PREFIX" \
  --with-decryption \
  --recursive \
  --region "$REGION" \
  --query 'Parameters[].[Name,Value]' \
  --output text | while IFS=$'\t' read -r name value; do
    key="$(basename "$name")"
    escaped="$(printf '%s' "$value" | sed "s/'/'\\\\''/g")"
    printf "%s='%s'\n" "$key" "$escaped"
done > "$tmp"

# Assemble DATABASE_URL at runtime from individual parameters — the full URL is
# never stored in SSM / Terraform state.
pg_user=$(grep '^POSTGRES_USER=' "$tmp" | head -1 | sed "s/^POSTGRES_USER='\(.*\)'$/\1/")
pg_pass=$(grep '^POSTGRES_PASSWORD=' "$tmp" | head -1 | sed "s/^POSTGRES_PASSWORD='\(.*\)'$/\1/")
pg_db=$(grep '^POSTGRES_DB=' "$tmp" | head -1 | sed "s/^POSTGRES_DB='\(.*\)'$/\1/")
pg_pass_escaped=$(printf '%s' "$pg_pass" | sed "s/'/'\\\\''/g")
printf "DATABASE_URL='postgresql+asyncpg://%s:%s@db:5432/%s'\n" \
  "$pg_user" "$pg_pass_escaped" "$pg_db" >> "$tmp"

install -m 600 -o ec2-user -g ec2-user "$tmp" "$OUT"
RENDER
chmod +x /usr/local/bin/vera-hr-render-env

# --- Render initial .env ---
/usr/local/bin/vera-hr-render-env "$${REGION}" "$${SSM_PREFIX}" "$${APP_DIR}/.env"
echo "[user-data] .env rendered"

# --- Pull initial config from S3 (populated by first GitHub Actions deploy). ---
# Best-effort: if the bucket has no config yet, the first deploy will populate it.
sudo -u ec2-user aws s3 sync "s3://$${S3_BUCKET}/config/" "$${APP_DIR}/" --region "$${REGION}" || true

touch "$${APP_DIR}/.bootstrapped"
chown ec2-user:ec2-user "$${APP_DIR}/.bootstrapped"

echo "[user-data] bootstrap complete"
