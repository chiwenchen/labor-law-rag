#!/usr/bin/env bash
# Promote (or demote) a user's access_role via SSM.
# Updates both the users row and all active auth_sessions so the change
# takes effect immediately without forcing the user to re-login.
#
# Usage:
#   ./scripts/promote-role.sh <email>              # defaults to admin
#   ./scripts/promote-role.sh <email> admin
#   ./scripts/promote-role.sh <email> hr
#   ./scripts/promote-role.sh <email> employee

set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
INSTANCE_ID="${INSTANCE_ID:-i-01e3050f148465f44}"

EMAIL="${1:-}"
ROLE="${2:-admin}"

if [[ -z "${EMAIL}" ]]; then
  echo "Usage: $0 <email> [admin|hr|employee]" >&2
  exit 2
fi

if [[ "${ROLE}" != "admin" && "${ROLE}" != "hr" && "${ROLE}" != "employee" ]]; then
  echo "Invalid role: ${ROLE} (must be admin / hr / employee)" >&2
  exit 2
fi

echo "[promote] ${EMAIL} -> ${ROLE} (instance ${INSTANCE_ID}, region ${REGION})"

# Shell command to run on EC2. Single-quote the SQL literals so psql sees them
# as strings; the outer shell handles interpolation of $EMAIL and $ROLE.
REMOTE_CMD="docker exec -i vera-hr-db-1 psql -U laborlaw -d laborlaw <<'SQL'
UPDATE users         SET access_role = '${ROLE}' WHERE email = '${EMAIL}';
UPDATE auth_sessions SET access_role = '${ROLE}' WHERE email = '${EMAIL}';
SELECT email, role, access_role, credits FROM users WHERE email = '${EMAIL}';
SQL"

# Wrap into a single-element commands array for SSM send-command.
# Write to a temp file to avoid newline/quote issues in shell expansion.
PARAMS_FILE="$(mktemp -t vera-hr-ssm.XXXXXX.json)"
trap 'rm -f "${PARAMS_FILE}"' EXIT
jq -n --arg cmd "${REMOTE_CMD}" '{commands: [$cmd]}' > "${PARAMS_FILE}"

cmd_id="$(aws ssm send-command \
  --instance-ids "${INSTANCE_ID}" \
  --document-name "AWS-RunShellScript" \
  --region "${REGION}" \
  --parameters "file://${PARAMS_FILE}" \
  --query 'Command.CommandId' \
  --output text)"

echo "[promote] SSM command: ${cmd_id}, waiting..."

status="Pending"
for _ in $(seq 1 20); do
  status="$(aws ssm get-command-invocation \
    --command-id "${cmd_id}" \
    --instance-id "${INSTANCE_ID}" \
    --region "${REGION}" \
    --query 'Status' --output text 2>/dev/null || echo Pending)"
  if [[ "${status}" == "Success" || "${status}" == "Failed" \
     || "${status}" == "Cancelled" || "${status}" == "TimedOut" ]]; then
    break
  fi
  sleep 3
done

aws ssm get-command-invocation \
  --command-id "${cmd_id}" \
  --instance-id "${INSTANCE_ID}" \
  --region "${REGION}" \
  --query 'StandardOutputContent' \
  --output text

if [[ "${status}" != "Success" ]]; then
  echo "[promote] FAILED (${status})"
  aws ssm get-command-invocation \
    --command-id "${cmd_id}" \
    --instance-id "${INSTANCE_ID}" \
    --region "${REGION}" \
    --query 'StandardErrorContent' --output text
  exit 1
fi

echo "[promote] done"
