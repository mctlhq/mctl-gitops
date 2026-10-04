# Vault (secrets.mctl.ai) signs in humans through ZITADEL. Vault's side (the
# auth/mctl mount, external groups, tenant policies) is declared by the
# vault-human-auth-iac Job (helm-charts/vault-human-auth-iac); this file
# declares who may sign in, and as what.
#
# Like Argo CD (argocd.tf): a project of its own, roles `admins` and one per
# tenant, and the user's roles on this project only in the `groups` claim
# (the shared groups action in argocd.tf). Vault maps `admins` to its admin
# policy and a tenant name to read access on that tenant's paths alone.
#
# Its own project, not `platform` or `Argo CD`: ZITADEL puts the client ids
# of every application of a project into `aud`, so a shared project would let
# another application's tokens carry Vault's audience. project_role_check
# refuses a token to anyone without a role here, so a tenant user is never
# let in by default.

locals {
  vault_url = "https://secrets.mctl.ai"
  # Vault's group alias for the admin policy (vault-human-auth-iac groups.tf).
  vault_admin_group = "admins"
}

resource "zitadel_project" "vault" {
  org_id = local.mctl_org_id
  name   = "Vault"

  project_role_check = true
  has_project_check  = true
  # Loads the user's grants into the token flow; without it the groups action
  # sees no grants (see zitadel_project.argocd).
  project_role_assertion = true

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_project_role" "vault_admin" {
  org_id       = local.mctl_org_id
  project_id   = zitadel_project.vault.id
  role_key     = local.vault_admin_group
  display_name = "Vault admin"
}

resource "zitadel_project_role" "vault_tenant" {
  for_each = local.tenants

  org_id       = local.mctl_org_id
  project_id   = zitadel_project.vault.id
  role_key     = each.key
  display_name = "Vault tenant ${each.key}"

  lifecycle {
    # A tenant named like the admin group would hand Vault's admin policy to
    # every opted-in user of that tenant.
    precondition {
      condition     = each.key != local.vault_admin_group
      error_message = "Tenant \"${each.key}\" collides with the Vault admin group; admins are granted through platform_admin_user_ids only."
    }
  }
}

# A tenant organization may hand out its own tenant role, and no other.
resource "zitadel_project_grant" "vault_tenant" {
  for_each = local.tenants

  org_id         = local.mctl_org_id
  project_id     = zitadel_project.vault.id
  granted_org_id = zitadel_org.tenant[each.key].id
  role_keys      = [zitadel_project_role.vault_tenant[each.key].role_key]
}

# Opt-in, like Argo CD: only a tenant user whose Vault entry carries
# "vault": true holds their tenant's role. Membership of a tenant
# organization alone grants no Vault access.
resource "zitadel_user_grant" "vault_tenant" {
  for_each = { for key, user in local.users : key => user if try(user.vault, false) == true }

  org_id           = zitadel_org.tenant[each.value.tenant].id
  user_id          = zitadel_human_user.tenant[each.key].id
  project_id       = zitadel_project.vault.id
  project_grant_id = zitadel_project_grant.vault_tenant[each.value.tenant].id
  role_keys        = [zitadel_project_role.vault_tenant[each.value.tenant].role_key]
}

# The platform admins, the same people as Argo CD's (admins.tf).
resource "zitadel_user_grant" "vault_admin" {
  for_each = local.platform_admin_user_ids

  org_id     = local.mctl_org_id
  user_id    = each.value
  project_id = zitadel_project.vault.id
  role_keys  = [zitadel_project_role.vault_admin.role_key]
}

# Vault's OIDC client serves both the UI and `vault login -method=oidc`: the
# auth mount holds one client. A confidential web client with code flow;
# Vault adds PKCE (S256) on every code-flow request. The CLI's loopback
# redirect is plain http, which ZITADEL accepts for a confidential client with
# the code flow without dev mode (zitadel/oidc ValidateAuthReqRedirectURI),
# and it is matched exactly, port included.
resource "zitadel_application_oidc" "vault" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.vault.id
  name       = "vault"

  app_type         = "OIDC_APP_TYPE_WEB"
  auth_method_type = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types      = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types   = ["OIDC_RESPONSE_TYPE_CODE"]
  # The UI callback carries the auth mount path (auth/mctl; the UI tab label
  # is the path). The CLI loopback has no mount path in it.
  redirect_uris = [
    "${local.vault_url}/ui/vault/auth/mctl/oidc/callback",
    "http://localhost:8250/oidc/callback",
  ]
  access_token_type = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode          = false
  # Vault reads `groups` from the ID token.
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "vault_oidc" {
  metadata {
    name      = "vault-oidc-zitadel"
    namespace = "vault-human-auth-iac"
  }

  # Read by the vault-human-auth-iac Job as TF_VAR_oidc_client_id,
  # TF_VAR_oidc_client_secret and TF_VAR_tenants. The tenant list is the one
  # the roles above come from, so Vault declares a group for exactly the
  # values the groups claim can carry, without reading secret/ itself.
  data = {
    client_id     = zitadel_application_oidc.vault.client_id
    client_secret = zitadel_application_oidc.vault.client_secret
    tenants       = jsonencode(sort(keys(local.tenants)))
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
