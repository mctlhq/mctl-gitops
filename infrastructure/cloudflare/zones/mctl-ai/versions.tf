terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # No backend block yet, for the same reason as the other two zone roots:
  # proving zero diff needs no write access, but keeping state on R2 does, and
  # the apply identity does not exist yet (#1111). Listed in
  # ../../.local-state-roots so the gap is visible in the gate rather than
  # absent from it.
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment — never from a
# .tf or .tfvars file.
provider "cloudflare" {}
