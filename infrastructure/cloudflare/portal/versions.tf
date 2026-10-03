terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment — never from a
# file. This root is the exception to the shared CI credentials: the
# repository-wide read token is zone-scoped ("read-only across the four
# zones", All zones, no account permission) and everything here is
# account-level, so cloudflare-plan.yml and cloudflare-drift.yml hand this
# root CF_PORTAL_READ_TOKEN instead, and cloudflare-apply.yml hands it
# CF_APPLY_TOKEN_PORTAL. Both are Account -> MCP Portals on this account
# alone, which is the narrowest permission group Cloudflare offers for this
# surface — no wider Zero Trust grant is involved.
provider "cloudflare" {}

variable "account_id" {
  description = "Cloudflare account (mashkovd)."
  type        = string
  default     = "6a09f637d20e1f66a8e9d45ebe778058"
}
