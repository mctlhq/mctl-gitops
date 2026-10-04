# Authorization: one external group per value of the groups claim.
#
#   admins    -> group human-admins, the existing `admin` policy. That policy
#                is the owner's, written by hand, and this root cannot change
#                it (its Vault policy only covers human-tenant-*).
#   <tenant>  -> group human-tenant-<tenant>, policy human-tenant-<tenant>:
#                read and write on that tenant's own paths, nothing else.
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

# Read and write on the tenant's own prefix (owner decision 2026-10-04).
#
#   - Write: create, update, patch, and delete of the latest version (KV v2
#     soft delete, or a chosen version through secret/delete/), plus
#     undelete. Every deleted version stays recoverable.
#   - Never destroy, and no metadata write or delete: purging a secret and
#     its history is for platform admins only.
#   - Platform-managed, read only: <service>/database. wft-provision-database
#     generates it and the cnpg-db-creds store syncs it into the shared-pg
#     role, so a human edit or delete would desynchronise the database login.
#     The `+` rules are more specific than `/*` and take precedence.
#
# The trailing `/*` stops a tenant name from matching another that starts
# with it. Nothing outside secret/{data,metadata,delete,undelete}/teams/<tenant>/.
resource "vault_policy" "tenant" {
  for_each = local.tenants

  name   = "human-tenant-${each.key}"
  policy = <<-EOT
    # Managed by vault-human-auth-iac (mctl-gitops helm-charts/vault-human-auth-iac).
    # Human members of tenant ${each.key}: read and write their own tenant's
    # secrets; never destroy; the platform-managed database credentials
    # read only.
    path "secret/data/teams/${each.key}/*" {
      capabilities = ["create", "read", "update", "patch", "delete", "list"]
    }

    path "secret/metadata/teams/${each.key}/*" {
      capabilities = ["read", "list"]
    }

    path "secret/delete/teams/${each.key}/*" {
      capabilities = ["update"]
    }

    path "secret/undelete/teams/${each.key}/*" {
      capabilities = ["update"]
    }

    path "secret/data/teams/${each.key}/+/database" {
      capabilities = ["read"]
    }

    path "secret/delete/teams/${each.key}/+/database" {
      capabilities = ["deny"]
    }

    path "secret/undelete/teams/${each.key}/+/database" {
      capabilities = ["deny"]
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
