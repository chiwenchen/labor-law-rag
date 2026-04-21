# SSM Parameter Store — one SecureString per env variable, read by EC2 at boot.
# DATABASE_URL is NOT stored here; it is assembled at runtime by
# /usr/local/bin/vera-hr-render-env from the individual POSTGRES_* parameters.
# This keeps the full connection string (and password) out of Terraform state.

locals {
  ssm_prefix = "/vera-hr"

  ssm_params = {
    "ANTHROPIC_API_KEY"     = var.anthropic_api_key
    "RESEND_API_KEY"        = var.resend_api_key
    "POSTGRES_USER"         = var.postgres_user
    "POSTGRES_PASSWORD"     = var.postgres_password
    "POSTGRES_DB"           = var.postgres_db
    "EMAIL_FROM"            = var.email_from
    "FRONTEND_URL"          = "https://${var.domain}"
    "BACKEND_URL"           = "http://backend:8000"
    "ENV"                   = "production"
    "SKIP_OTP_VERIFICATION" = "false"
    "SKIP_OTP_EMAIL"        = "false"
    "DOMAIN"                = var.domain
    "API_DOMAIN"            = var.api_domain
  }
}

resource "aws_ssm_parameter" "env" {
  for_each = local.ssm_params

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "SecureString"
  value = each.value

  tags = {
    Name = "${local.name_prefix}-${each.key}"
  }
}
