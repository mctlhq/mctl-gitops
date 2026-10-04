# Proof, on every plan of this root, that the plan identity can see the
# account's Access identity providers (#1500).
#
# It could not until 2026-10-04: CF_ACCOUNT_READ_TOKEN carried only
# `Access: Apps and Policies Read`, and an identity-provider lookup with it
# returned an empty list rather than an error (projects-mcp.tf). Once this
# root declares an identity provider (zitadel-idp.tf), a blind refresh would
# be read as "the provider is gone" and planned as a create, which is a
# failed read reported as absence. The token now also carries
# `Access: Identity Providers Read`.
#
# The two providers every application here already names must be in the
# list. A token that loses the scope, or a listing that comes back short,
# fails the plan here instead of passing as an empty account.

data "cloudflare_zero_trust_access_identity_providers" "all" {
  account_id = var.account_id

  lifecycle {
    postcondition {
      condition = alltrue([
        for id in [var.projects_mcp_google_idp_id, var.projects_mcp_otp_idp_id] :
        contains([for idp in self.result : idp.id], id)
      ])
      error_message = "The plan identity cannot see the account's Access identity providers: the Google or the one-time PIN provider (or both) is missing from the listing. CF_ACCOUNT_READ_TOKEN needs `Access: Identity Providers Read`."
    }
  }
}
