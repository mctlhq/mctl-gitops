# Grants the coolify-mcp Kubernetes-auth role exactly what mctl-coolify-mcp's
# multi-tenant mode needs: read/write on its own tenant records and OAuth
# state, under its own team path, and nothing else.
#
# No "delete" capability anywhere: KV v2's delete is a tombstone that hides
# the current version while every prior one stays readable, so a revocation
# built on it would not revoke. "destroy" is the only removal path granted,
# matching how VaultClient.destroy() (mctl-coolify-mcp's own Vault client)
# is implemented — see src/lib/vault.ts.

path "secret/data/teams/labs/coolify-mcp/*" {
  capabilities = ["create", "read", "update"]
}

path "secret/metadata/teams/labs/coolify-mcp/*" {
  capabilities = ["read", "update", "list"]
}

path "secret/destroy/teams/labs/coolify-mcp/*" {
  capabilities = ["update"]
}
