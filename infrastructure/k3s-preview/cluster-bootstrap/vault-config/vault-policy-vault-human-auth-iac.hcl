# The vault-human-auth-iac Job (helm-charts/vault-human-auth-iac): declares
# human sign-in through ZITADEL. It manages the auth/mctl mount, external
# identity groups and their aliases, the human-tenant-* policies, and the
# `stdout` audit device that records what those identities do.
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

# The OIDC auth mount (path mctl: the Vault UI labels the login tab with the
# mount path), and no other. Enabling an auth mount needs sudo; no
# delete, so the Job can never disable it.
path "sys/auth/mctl" {
  capabilities = ["create", "update", "sudo"]
}

# The provider reads the mount back through sys/mounts/auth/<path>.
path "sys/mounts/auth/mctl" {
  capabilities = ["read"]
}

path "sys/mounts/auth/mctl/tune" {
  capabilities = ["read", "update"]
}

# Its config and roles.
path "auth/mctl/config" {
  capabilities = ["create", "read", "update"]
}

path "auth/mctl/role/*" {
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

# The audit device (iac/audit.tf), at path stdout and no other. Enabling one
# needs sudo, and so does listing them, which is how the provider reads the
# device back. No delete: the Job can enable the device and re-enable it if
# someone disables it, but never disable it, and never replace it. A device
# that already exists cannot be re-enabled with other options either (Vault
# answers "path already in use"), so after the first apply this grant only
# repairs.
path "sys/audit" {
  capabilities = ["read", "sudo"]
}

path "sys/audit/stdout" {
  capabilities = ["update", "sudo"]
}
