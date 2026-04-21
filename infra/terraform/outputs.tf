output "instance_id" {
  value       = aws_instance.app.id
  description = "EC2 instance ID — use with SSM Session Manager"
}

output "elastic_ip" {
  value       = aws_eip.app.public_ip
  description = "Point vera-hr and api-vera-hr A records at this IP in Cloudflare"
}

output "app_bucket" {
  value       = aws_s3_bucket.app.bucket
  description = "S3 bucket for config sync + pg_dump backups"
}

output "github_deploy_role_arn" {
  value       = aws_iam_role.github_deploy.arn
  description = "Set as AWS_DEPLOY_ROLE_ARN in GitHub repo variables"
}

output "ssm_session_command" {
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.region}"
  description = "Run this on your Mac to SSH (no key needed)"
}
