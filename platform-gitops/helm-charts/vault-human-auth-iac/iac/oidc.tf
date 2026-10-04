# Vault's auth/oidc mount, signing humans in through ZITADEL. The client is
# the `vault` application of ZITADEL's "Vault" project (zitadel-iac vault.tf):
# a project of its own, so the tokens Vault accepts carry no other
# application's audience, and only users holding a role on it can obtain one
# (project_role_check), so a tenant user without the opt-in is refused by
# ZITADEL before Vault sees them.
#
# Code flow with PKCE: Vault's OIDC plugin sends an S256 challenge on every
# code-flow request, and ZITADEL checks it on top of the client secret.

locals {
  issuer    = "https://auth.mctl.ai"
  vault_url = "https://secrets.mctl.ai"
}

resource "vault_jwt_auth_backend" "oidc" {
  path        = "oidc"
  type        = "oidc"
  description = "Human sign-in through ZITADEL (auth.mctl.ai)"

  oidc_discovery_url = local.issuer
  bound_issuer       = local.issuer
  oidc_client_id     = var.oidc_client_id
  oidc_client_secret = var.oidc_client_secret
  # `vault login -method=oidc` and the UI need no role name.
  default_role = "zitadel"

  tune {
    # Shown in the UI's method list before sign-in.
    listing_visibility = "unauth"
    default_lease_ttl  = "1h"
    max_lease_ttl      = "8h"
    token_type         = "default-service"
  }
}

resource "vault_jwt_auth_backend_role" "zitadel" {
  backend   = vault_jwt_auth_backend.oidc.path
  role_name = "zitadel"
  role_type = "oidc"

  # The ZITADEL user id: stable across renames, unlike a login name. The
  # entity alias is keyed on it; e-mail and login name are kept as alias
  # metadata, so the audit log says who acted.
  user_claim = "sub"
  claim_mappings = {
    email              = "email"
    preferred_username = "username"
  }

  # The groups claim carries the user's roles on the Vault project only:
  # `admins`, or the user's own tenant (zitadel-iac argocd.tf, the groups
  # action). Each value is matched against the group aliases in groups.tf.
  groups_claim    = "groups"
  bound_audiences = [var.oidc_client_id]
  oidc_scopes     = ["openid", "profile", "email"]

  allowed_redirect_uris = [
    "${local.vault_url}/ui/vault/auth/${vault_jwt_auth_backend.oidc.path}/oidc/callback",
    # `vault login -method=oidc` listens here.
    "http://localhost:8250/oidc/callback",
  ]

  # Short-lived: a human token is an admin token for some, and nothing about
  # an interactive session needs more. No policy of its own; everything comes
  # from the groups.
  token_ttl      = 3600
  token_max_ttl  = 28800
  token_policies = []
}
