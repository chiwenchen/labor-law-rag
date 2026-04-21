terraform {
  backend "s3" {
    # Values are injected via `terraform init -backend-config=...` in CI,
    # or set here after running infra/bootstrap/bootstrap.sh.
    # Example (uncomment & fill with your account id):
    # bucket         = "vera-hr-tfstate-123456789012"
    # key            = "vera-hr/prod/terraform.tfstate"
    # region         = "ap-northeast-1"
    # dynamodb_table = "vera-hr-tfstate-lock"
    # encrypt        = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "vera-hr"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  project     = "vera-hr"
  name_prefix = "${local.project}-prod"
  account_id  = data.aws_caller_identity.current.account_id
}
