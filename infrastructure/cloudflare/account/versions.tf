terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment.
provider "cloudflare" {}

variable "account_id" {
  description = "Cloudflare account (mashkovd)."
  type        = string
  default     = "6a09f637d20e1f66a8e9d45ebe778058"
}
