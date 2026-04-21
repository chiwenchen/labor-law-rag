# Deployment Guide — AWS EC2

Production target: single `t4g.medium` EC2 in `ap-northeast-1` running Docker Compose, fronted by Cloudflare. Fully automated from GitHub Actions (push to `main`).

## Architecture

```
user ─→ Cloudflare (DNS + proxy + WAF)
         ├─ vera-hr.redarch.dev       ─→ EC2:443 ─→ Caddy ─→ Next.js :3000
         └─ api-vera-hr.redarch.dev   ─→ EC2:443 ─→ Caddy ─→ FastAPI :8000 ─→ pgvector :5432

EC2 instance profile → S3 (config sync + pg_dump) + SSM Parameter Store (secrets)
GitHub Actions       → OIDC role → Terraform apply + GHCR push + SSM send-command
```

## One-time bootstrap

### 1. Install CLIs
Already on your Mac: `aws`, `gh`, `docker`. Need `terraform`:
```bash
brew install terraform
```

### 2. Provision Terraform backend + GitHub OIDC provider
```bash
cd infra/bootstrap
./bootstrap.sh
```
Creates:
- `s3://vera-hr-tfstate-<account_id>` (state bucket, versioned + encrypted)
- `vera-hr-tfstate-lock` (DynamoDB table)
- GitHub Actions OIDC provider

### 3. Fill Terraform vars
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars — fill in anthropic_api_key, resend_api_key, postgres_password
```

### 4. First `terraform apply`
```bash
terraform init \
  -backend-config="bucket=vera-hr-tfstate-$(aws sts get-caller-identity --query Account --output text)" \
  -backend-config="key=vera-hr/prod/terraform.tfstate" \
  -backend-config="region=ap-northeast-1" \
  -backend-config="dynamodb_table=vera-hr-tfstate-lock" \
  -backend-config="encrypt=true"

terraform plan
terraform apply
```

Outputs to note:
- `elastic_ip` → point Cloudflare DNS at this
- `github_deploy_role_arn` → set as GitHub repo variable
- `app_bucket` → used by GitHub Actions

### 5. Configure Cloudflare DNS
In Cloudflare dashboard for `redarch.dev`:
- `A  vera-hr      → <elastic_ip>  Proxied (orange cloud)`
- `A  api-vera-hr  → <elastic_ip>  Proxied (orange cloud)`
- SSL/TLS mode: **Full (strict)**

### 6. Wire up GitHub Actions
Repo → Settings → Secrets and variables → Actions:

**Variables (not sensitive):**
- `AWS_DEPLOY_ROLE_ARN` = output from Terraform
- `AWS_ACCOUNT_ID` = `aws sts get-caller-identity --query Account --output text`

**Secrets (for Terraform apply on changes):**
- `ANTHROPIC_API_KEY`
- `RESEND_API_KEY`
- `POSTGRES_PASSWORD`

### 7. First deploy
```bash
git checkout -b feat/ec2-deploy
git add .
git commit -m "feat: AWS EC2 deploy with Terraform + GHCR + SSM"
gh pr create --fill
# merge PR → `main` push triggers the deploy workflow
```

## Day-2 operations

### SSH into the box
```bash
aws ssm start-session --target <instance_id> --region ap-northeast-1
# then: sudo su - ec2-user
```

### View logs
```bash
cd /opt/vera-hr
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f caddy
```

### Force a redeploy without code changes
```bash
gh workflow run deploy.yml
```

### Manual backup
```bash
# on EC2
cd /opt/vera-hr && ./backup.sh
```

### Restore from backup
```bash
# on EC2
cd /opt/vera-hr && ./restore.sh                 # latest
./restore.sh backups/pgdump-20260422T190000Z.sql.gz  # specific
```

### Rotate secrets
```bash
aws ssm put-parameter \
  --name /vera-hr/ANTHROPIC_API_KEY \
  --value "sk-ant-new-key" \
  --type SecureString \
  --overwrite \
  --region ap-northeast-1

# then trigger a redeploy so EC2 re-renders .env
gh workflow run deploy.yml
```

## Cost (April 2026, ap-northeast-1)

| Item | Monthly |
|------|---------|
| EC2 `t4g.medium` (on-demand 730h) | $24.53 |
| 30GB gp3 EBS | $2.40 |
| Elastic IP (attached) | $0 |
| S3 storage (< 3GB) | $0.07 |
| DynamoDB (tfstate lock, pay-per-request) | ~$0 |
| Data transfer out (assume 20GB) | $0.80 |
| **Total** | **~$28** |

Drop to **~$18** after 12 months with a 1-year Compute Savings Plan commitment.

## Upgrade triggers

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU p95 > 70% sustained 1 week | | `t4g.medium` → `t4g.large` (+$15/mo) |
| RAM pressure (swap > 50% used) | | Upsize instance |
| DB > 10GB | | Extract to RDS `db.t4g.micro` (+$17/mo) |
| p99 latency > 2s | | Add ElastiCache Redis nano (+$12/mo) |
| DAU > 3000 | | Multi-region or managed platform (Fly/Supabase) |

## Disaster recovery RTO/RPO

- **RPO**: worst 24 h (daily backup)
- **RTO**: < 15 min
  1. `terraform apply` rebuilds EC2 from AMI (5 min)
  2. `./restore.sh` pulls latest backup from S3 and loads (2 min)
  3. `docker compose up -d` brings stack back (5 min, includes bge-m3 first-request warm-up)

## Security posture

- No SSH port open (SSM Session Manager only)
- IMDSv2 enforced
- Security group only allows 80/443 from Cloudflare edge IPv4 ranges (auto-fetched at apply time)
- EBS encrypted at rest
- S3 bucket: private, versioned, SSE-S3, lifecycle expires backups at 7 days
- Secrets: SSM Parameter Store (SecureString, KMS-encrypted)
- IAM: least-privilege — EC2 role scoped to its own bucket + its own SSM prefix; GitHub OIDC role scoped to `refs/heads/main`
- OS: `dnf-automatic` applies security updates nightly
