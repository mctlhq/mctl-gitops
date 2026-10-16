terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment. Plan and
# drift hand this root CF_ACCOUNT_READ_TOKEN, which carries
# `Account API Tokens Read`. The root declares no resources, so there is
# nothing to apply and cloudflare-apply.yml has no write token for it: its
# chain resolves to the empty string and the apply is refused.
provider "cloudflare" {}

variable "account_id" {
  description = "Cloudflare account (mashkovd)."
  type        = string
  default     = "6a09f637d20e1f66a8e9d45ebe778058"
}
