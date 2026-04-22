variable "region" {
  type        = string
  default     = "ap-northeast-1"
  description = "AWS region"
}

variable "instance_type" {
  type        = string
  default     = "t4g.medium"
  description = "EC2 instance type (Graviton ARM64)"
}

variable "root_volume_size_gb" {
  type        = number
  default     = 30
  description = "Root EBS volume size in GB"
}

variable "github_repo" {
  type        = string
  default     = "chiwenchen/labor-law-rag"
  description = "GitHub repo allowed to assume the deploy role (owner/repo)"
}

variable "github_branch" {
  type        = string
  default     = "main"
  description = "Branch allowed to assume the deploy role"
}

variable "domain" {
  type        = string
  default     = "vera-hr.redarch.dev"
  description = "Primary frontend domain"
}

variable "api_domain" {
  type        = string
  default     = "api-vera-hr.redarch.dev"
  description = "Backend API domain"
}

# --- Secrets (set via terraform.tfvars, never committed) ---

variable "anthropic_api_key" {
  type      = string
  sensitive = true
}

variable "resend_api_key" {
  type      = string
  sensitive = true
}

variable "email_from" {
  type        = string
  default     = "noreply@redarch.dev"
  description = "Resend requires the exact domain verified. redarch.dev is verified; subdomains like vera-hr.redarch.dev need separate verification."
}

variable "postgres_user" {
  type    = string
  default = "laborlaw"
}

variable "postgres_password" {
  type      = string
  sensitive = true
}

variable "postgres_db" {
  type    = string
  default = "laborlaw"
}
