# ZITADEL sign-in to the MCP portal (mcp.mctl.ai) and its members (#1500).
#
# The Google client behind the account's Google provider dies around
# 2026-10-17 (#1328), and the portal's pilot policies admit two addresses by
# e-mail, whichever provider asserted them. This adds a second door that
# names no one: any login through the ZITADEL provider (zitadel-idp.tf).
#
# The authorization is ZITADEL's, not this policy's. The client Access uses
# belongs to the ZITADEL project `Cloudflare Access`, with project_role_check
# and has_project_check, and its `access` role is held only by the platform
# admins (zitadel-iac iac/cloudflare-access.tf, argocd_admin_users). Anyone
# else, every tenant user included, is refused by ZITADEL with
# Errors.User.GrantRequired before Access sees them. Matching e-mails here as
# well would repeat that list in a public repository.
#
# allowed_idps stays as it is: the portal and its members hold `[]`, which
# Access reads as every provider in the account, so the ZITADEL button has
# been on their login pages since zitadel-idp.tf applied. Until this policy
# exists a ZITADEL login there passes only if its e-mail is a pilot address.
#
# Reusable, and attached at precedence 2 after each application's existing
# pilot policy, which is left exactly as it is.
resource "cloudflare_zero_trust_access_policy" "zitadel_access_role" {
  account_id = var.account_id
  name       = "ZITADEL access role (auth.mctl.ai)"
  decision   = "allow"

  include = [
    { login_method = { id = cloudflare_zero_trust_access_identity_provider.zitadel.id } },
  ]
}
