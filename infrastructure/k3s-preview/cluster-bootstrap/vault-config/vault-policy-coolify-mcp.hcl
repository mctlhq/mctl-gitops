# Grants the coolify-mcp Kubernetes-auth role exactly what mctl-coolify-mcp's
# multi-tenant mode needs, on its OWN dedicated KV v2 mount
# (`coolify-mcp-users/`) — not a subpath of the shared `secret/` mount used by
# every other team, since the app's VaultConfig.mount is used verbatim as the
# Vault API path segment (`${mount}/data/${key}`), which only works if that
# mount actually exists at that path. Enabling a small dedicated mount, one
# per hosted service that needs its own write path, keeps this server's
# credentials off a shared mount's ACL surface entirely.
#
# No "delete" capability anywhere: KV v2's delete is a tombstone that hides
# the current version while every prior one stays readable, so a revocation
# built on it would not revoke. "destroy" is the only removal path granted,
# matching how VaultClient.destroy() (mctl-coolify-mcp's own Vault client)
# is implemented — see src/lib/vault.ts.
#
# "create" is required on metadata/*, not just data/*: Vault's ACL treats a
# POST to a metadata path that does not yet exist as "create", not "update"
# — every brand-new key's first write (the oauth-state key on first boot, or
# any tenant's first enrolment) hits this before it hits data/*, since
# VaultClient.write() sets metadata (max_versions) before writing data. Without
# it, every first write 403s: caught live on the real deployment 2026-09-20,
# after this same omission had already been applied to the real Vault by this
# PR's own first two commits.

path "coolify-mcp-users/data/*" {
  capabilities = ["create", "read", "update"]
}

path "coolify-mcp-users/metadata/*" {
  capabilities = ["create", "read", "update", "list"]
}

path "coolify-mcp-users/destroy/*" {
  capabilities = ["update"]
}
