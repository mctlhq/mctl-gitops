terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # Backend declared in backend.tf.
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment — never from a
# .tf or .tfvars file. Read-only scope (Zone:Zone:Read + Zone:DNS:Read on
# mctl.ru) is sufficient for import and plan; no write scope is needed to prove
# zero diff.
provider "cloudflare" {}
