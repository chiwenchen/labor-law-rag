data "aws_ami" "al2023_arm" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-kernel-6.1-arm64"]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023_arm.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  user_data = templatefile("${path.module}/user_data.sh", {
    region     = var.region
    ssm_prefix = "/vera-hr"
    s3_bucket  = aws_s3_bucket.app.bucket
    project    = local.project
  })
  # user_data runs ONCE on first boot. Changing user_data.sh does NOT re-run it
  # and does NOT replace the instance. To re-bootstrap, run:
  #   terraform taint aws_instance.app && terraform apply
  user_data_replace_on_change = false

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
    tags = {
      Name = "${local.name_prefix}-root"
    }
  }

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_endpoint               = "enabled"
    # hop_limit = 1 blocks containers from reaching IMDS — narrows SSRF attack
    # surface. Host-level scripts (backup.sh, deploy.sh) still have access since
    # they run directly on the VM, not inside a container.
    http_put_response_hop_limit = 1
  }

  lifecycle {
    ignore_changes = [ami] # avoid accidental instance replacement on new AMI releases
  }

  tags = {
    Name = "${local.name_prefix}-app"
  }
}

resource "aws_eip" "app" {
  domain = "vpc"
  tags = {
    Name = "${local.name_prefix}-app"
  }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
