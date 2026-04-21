#!/usr/bin/env bash
# One-time bootstrap: creates Terraform S3 backend + DynamoDB lock + GitHub OIDC provider.
# Run this ONCE from your Mac before `terraform init`.
#
# Usage:
#   export AWS_PROFILE=default   # or ClaudeCLI
#   ./infra/bootstrap/bootstrap.sh

set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
PROJECT="vera-hr"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
TFSTATE_BUCKET="${PROJECT}-tfstate-${ACCOUNT_ID}"
TFSTATE_LOCK_TABLE="${PROJECT}-tfstate-lock"

echo "Account:  ${ACCOUNT_ID}"
echo "Region:   ${REGION}"
echo "Bucket:   ${TFSTATE_BUCKET}"
echo "DDB:      ${TFSTATE_LOCK_TABLE}"
read -rp "Proceed? [y/N] " yn
[[ "${yn}" == "y" || "${yn}" == "Y" ]] || exit 1

# --- S3 bucket for tfstate ---
if aws s3api head-bucket --bucket "${TFSTATE_BUCKET}" 2>/dev/null; then
  echo "S3 bucket already exists: ${TFSTATE_BUCKET}"
else
  aws s3api create-bucket \
    --bucket "${TFSTATE_BUCKET}" \
    --region "${REGION}" \
    --create-bucket-configuration "LocationConstraint=${REGION}"
  aws s3api put-bucket-versioning \
    --bucket "${TFSTATE_BUCKET}" \
    --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption \
    --bucket "${TFSTATE_BUCKET}" \
    --server-side-encryption-configuration \
      '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-public-access-block \
    --bucket "${TFSTATE_BUCKET}" \
    --public-access-block-configuration \
      'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
  echo "Created S3 bucket: ${TFSTATE_BUCKET}"
fi

# --- DynamoDB lock table ---
if aws dynamodb describe-table --table-name "${TFSTATE_LOCK_TABLE}" --region "${REGION}" 2>/dev/null >/dev/null; then
  echo "DynamoDB table already exists: ${TFSTATE_LOCK_TABLE}"
else
  aws dynamodb create-table \
    --table-name "${TFSTATE_LOCK_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${REGION}" >/dev/null
  aws dynamodb wait table-exists --table-name "${TFSTATE_LOCK_TABLE}" --region "${REGION}"
  echo "Created DynamoDB table: ${TFSTATE_LOCK_TABLE}"
fi

# --- GitHub OIDC provider ---
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "${OIDC_ARN}" 2>/dev/null >/dev/null; then
  echo "OIDC provider already exists"
else
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
  echo "Created GitHub OIDC provider"
fi

cat <<EOF

Bootstrap complete.

Next step — create infra/terraform/terraform.tfvars from the example, then:

  cd infra/terraform
  terraform init
  terraform plan
  terraform apply

Backend config (already in main.tf):
  bucket         = "${TFSTATE_BUCKET}"
  dynamodb_table = "${TFSTATE_LOCK_TABLE}"
  region         = "${REGION}"
EOF
