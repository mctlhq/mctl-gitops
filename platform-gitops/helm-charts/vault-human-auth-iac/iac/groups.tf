# Authorization: one external group per value of the groups claim.
#
#   admins    -> group human-admins, the existing `admin` policy. That policy
#                is the owner's, written by hand, and this root cannot change
#                it (its Vault policy only covers human-tenant-*).
#   <tenant>  -> group human-tenant-<tenant>, policy human-tenant-<tenant>:
#                read and list on that tenant's own paths, nothing else.
#
# Membership is decided at login from the claim, so removing a user's role in
# ZITADEL removes their access at their next login (tokens live an hour).

locals {
  admin_group = "admins"
  tenants     = toset(jsondecode(var.tenants))
}

resource "vault_identity_group" "admins" {
  name     = "human-admins"
  type     = "external"
  policies = ["admin"]

  metadata = {
    managed-by = "vault-human-auth-iac"
  }
}

resource "vault_identity_group_alias" "admins" {
  name           = local.admin_group
  mount_accessor = vault_jwt_auth_backend.oidc.accessor
  canonical_id   = vault_identity_group.admins.id
}

# Read-only. Tenant secrets are written through the portal (Backstage, with
# its own backstage-teams-rw role) and by the platform workflows, never by a
# human token, so nothing here needs create, update or delete. The trailing
# `/*` stops a tenant name from matching another that starts with it.
resource "vault_policy" "tenant" {
  for_each = local.tenants

  name   = "human-tenant-${each.key}"
  policy = <<-EOT
    # Managed by vault-human-auth-iac (mctl-gitops helm-charts/vault-human-auth-iac).
    # Human members of tenant ${each.key}: read their own tenant's secrets.
    path "secret/data/teams/${each.key}/*" {
      capabilities = ["read"]
    }

    path "secret/metadata/teams/${each.key}/*" {
      capabilities = ["read", "list"]
    }
  EOT
}

resource "vault_identity_group" "tenant" {
  for_each = local.tenants

  name     = "human-tenant-${each.key}"
  type     = "external"
  policies = [vault_policy.tenant[each.key].name]

  metadata = {
    managed-by = "vault-human-auth-iac"
    tenant     = each.key
  }
}

resource "vault_identity_group_alias" "tenant" {
  for_each = local.tenants

  name           = each.key
  mount_accessor = vault_jwt_auth_backend.oidc.accessor
  canonical_id   = vault_identity_group.tenant[each.key].id
}
