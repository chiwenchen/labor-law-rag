data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Cloudflare edge ranges — refreshed at every `terraform apply`.
data "http" "cloudflare_ipv4" {
  url = "https://www.cloudflare.com/ips-v4"
}

data "http" "cloudflare_ipv6" {
  url = "https://www.cloudflare.com/ips-v6"
}

locals {
  cloudflare_ipv4_cidrs = compact(split("\n", trimspace(data.http.cloudflare_ipv4.response_body)))
  cloudflare_ipv6_cidrs = compact(split("\n", trimspace(data.http.cloudflare_ipv6.response_body)))
}

resource "aws_security_group" "ec2" {
  name        = "${local.name_prefix}-ec2"
  description = "Vera HR EC2 — HTTPS/HTTP from Cloudflare only (v4+v6), no SSH (use SSM)"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "${local.name_prefix}-ec2"
  }
}

# --- IPv4 ingress from Cloudflare ---
resource "aws_vpc_security_group_ingress_rule" "https_v4" {
  for_each          = toset(local.cloudflare_ipv4_cidrs)
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = each.value
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS from Cloudflare (v4)"
}

resource "aws_vpc_security_group_ingress_rule" "http_v4" {
  for_each          = toset(local.cloudflare_ipv4_cidrs)
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = each.value
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP (LE HTTP-01 + redirect) from Cloudflare (v4)"
}

# --- IPv6 ingress from Cloudflare ---
resource "aws_vpc_security_group_ingress_rule" "https_v6" {
  for_each          = toset(local.cloudflare_ipv6_cidrs)
  security_group_id = aws_security_group.ec2.id
  cidr_ipv6         = each.value
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS from Cloudflare (v6)"
}

resource "aws_vpc_security_group_ingress_rule" "http_v6" {
  for_each          = toset(local.cloudflare_ipv6_cidrs)
  security_group_id = aws_security_group.ec2.id
  cidr_ipv6         = each.value
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP (LE HTTP-01 + redirect) from Cloudflare (v6)"
}

# --- Egress ---
resource "aws_vpc_security_group_egress_rule" "all_out_v4" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress v4"
}

resource "aws_vpc_security_group_egress_rule" "all_out_v6" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv6         = "::/0"
  ip_protocol       = "-1"
  description       = "All egress v6"
}
