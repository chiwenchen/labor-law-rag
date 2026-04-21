# ======================================================================
# EC2 instance profile: SSM Session Manager + S3 backup + SSM Parameters
# ======================================================================

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${local.name_prefix}-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ec2_ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "ec2_app" {
  # Read env secrets from SSM Parameter Store (scoped to /vera-hr/* only)
  statement {
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:${var.region}:${local.account_id}:parameter/vera-hr/*",
    ]
  }

  # Decrypt SecureString parameters — only the AWS-managed SSM key.
  # (If a customer-managed KMS key is added later, reference it by ARN explicitly.)
  statement {
    actions = ["kms:Decrypt"]
    resources = [
      "arn:aws:kms:${var.region}:${local.account_id}:alias/aws/ssm",
    ]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }

  # Read config + write backups to the app bucket
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.app.arn,
      "${aws_s3_bucket.app.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "ec2_app" {
  name   = "${local.name_prefix}-ec2-app"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_app.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${local.name_prefix}-ec2"
  role = aws_iam_role.ec2.name
}

# ======================================================================
# GitHub Actions OIDC deploy role
# ======================================================================

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Use StringEquals (not StringLike) so wildcards can't weaken the sub claim.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/${var.github_branch}"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${local.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

data "aws_iam_policy_document" "github_deploy" {
  # Terraform backend — state + lock
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = ["arn:aws:s3:::vera-hr-tfstate-${local.account_id}"]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::vera-hr-tfstate-${local.account_id}/*"]
  }
  statement {
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = ["arn:aws:dynamodb:${var.region}:${local.account_id}:table/vera-hr-tfstate-lock"]
  }

  # Sync deploy/ configs to app bucket
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.app.arn,
      "${aws_s3_bucket.app.arn}/*",
    ]
  }

  # Send deploy shell commands only to OUR instance via the standard doc.
  statement {
    actions = [
      "ssm:SendCommand",
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = [
      "arn:aws:ec2:${var.region}:${local.account_id}:instance/${aws_instance.app.id}",
      "arn:aws:ssm:${var.region}::document/AWS-RunShellScript",
    ]
  }

  # DescribeInstanceInformation does not support resource-level restrictions.
  statement {
    actions   = ["ssm:DescribeInstanceInformation"]
    resources = ["*"]
  }

  # Read-only describes for Terraform plan/apply
  statement {
    actions = [
      "ec2:Describe*",
      "iam:Get*",
      "iam:List*",
    ]
    resources = ["*"]
  }

  # PassRole — scoped to the EC2 instance role only, via EC2 service.
  # Prevents attaching any other role (e.g. AdministratorAccess) to a new instance.
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.ec2.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${local.name_prefix}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
