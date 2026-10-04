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
