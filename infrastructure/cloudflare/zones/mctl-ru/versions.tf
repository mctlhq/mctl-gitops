terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # No backend block yet. The zero-diff pilot (#1087) runs against a local state
  # file so it can be thrown away without touching shared infrastructure; the R2
  # backend and its state key arrive with the control-plane bootstrap (#1093).
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment — never from a
# .tf or .tfvars file. Read-only scope (Zone:Zone:Read + Zone:DNS:Read on
# mctl.ru) is sufficient for import and plan; no write scope is needed to prove
# zero diff.
provider "cloudflare" {}
