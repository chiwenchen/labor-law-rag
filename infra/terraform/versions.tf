terraform {
  required_version = "~> 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
}
