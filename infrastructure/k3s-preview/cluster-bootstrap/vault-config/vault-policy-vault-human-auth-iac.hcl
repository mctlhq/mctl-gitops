# The vault-human-auth-iac Job (helm-charts/vault-human-auth-iac): declares
# human sign-in through ZITADEL. It manages the auth/oidc mount, external
# identity groups and their aliases, and the human-tenant-* policies.
#
# No secret data: nothing under secret/ or any other secrets engine, no
# token creation, no other auth mount, no other policy name.
#
# Not a sandbox, though: a root that writes ACL policies and decides which
# group carries which policy can hand any ZITADEL identity any access,
# `admin` included. What bounds it is that its inputs are this public
# repository (reviewed, merged to main) and the ZITADEL client it reads from
# its own namespace. Treat a change to that chart like a change to Vault's
# admin policy.
#
# Apply once (owner, admin token): see the README, "vault-human-auth-iac".

# The OIDC auth mount, and no other. Enabling an auth mount needs sudo; no
# delete, so the Job can never disable it.
path "sys/auth/oidc" {
  capabilities = ["create", "update", "sudo"]
}

# The provider reads the mount back through sys/mounts/auth/<path>.
path "sys/mounts/auth/oidc" {
  capabilities = ["read"]
}

path "sys/mounts/auth/oidc/tune" {
  capabilities = ["read", "update"]
}

# Its config and roles.
path "auth/oidc/config" {
  capabilities = ["create", "read", "update"]
}

path "auth/oidc/role/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# External groups and their aliases. Vault addresses them by id, so these
# cannot be narrowed by name.
path "identity/group" {
  capabilities = ["create", "update"]
}

path "identity/group/*" {
  capabilities = ["read", "update", "delete"]
}

path "identity/group-alias" {
  capabilities = ["create", "update"]
}

path "identity/group-alias/*" {
  capabilities = ["read", "update", "delete"]
}

# The tenant policies, by prefix only.
path "sys/policies/acl/human-tenant-*" {
  capabilities = ["create", "read", "update", "delete"]
}

# The move of the human login mount from auth/oidc to auth/mctl (the Vault UI
# labels the login tab with the mount path). Temporary: everything below is
# for the oidc->mctl move and is removed again in the cleanup step (d), so the
# Job keeps no standing remount ability. Each block was proven necessary on a
# local Vault 1.17.2 by removing it: without any one of them the move fails
# with a 403 mid-apply. `sys/auth/mctl` is not needed for the move itself.

# One remount, and only this one: any other from/to is refused. The move keeps
# the mount's accessor, so entity and group aliases carry over.
# For the oidc->mctl move, removed again in (d).
path "sys/remount" {
  capabilities = ["update", "sudo"]
  allowed_parameters = {
    "from" = ["auth/oidc"]
    "to"   = ["auth/mctl"]
  }
}

# The provider polls the move's migration status.
# For the oidc->mctl move, removed again in (d).
path "sys/remount/status/*" {
  capabilities = ["read"]
}

# The mount, its tune and its config and roles, read back at the new path.
# For the oidc->mctl move, removed again in (d) (replaced there by the same
# grants on mctl in place of the oidc ones above).
path "sys/mounts/auth/mctl" {
  capabilities = ["read"]
}

path "sys/mounts/auth/mctl/tune" {
  capabilities = ["read", "update"]
}

path "auth/mctl/config" {
  capabilities = ["create", "read", "update"]
}

path "auth/mctl/role/*" {
  capabilities = ["create", "read", "update", "delete"]
}
