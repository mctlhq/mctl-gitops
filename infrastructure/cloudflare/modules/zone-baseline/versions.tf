# A module, not a root: it declares which provider it needs but configures
# none. Both cloudflare workflows prune infrastructure/cloudflare/modules/*
# from root discovery, and the coverage guard exempts these files from its
# orphan-configuration check, so this versions.tf does not make the directory
# look like a root.
terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}
