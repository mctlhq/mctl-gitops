# Backstage: read/write team secrets (for scaffolder templates)
# Used by the VAULT_TOKEN injected into Backstage via backstage-secrets ExternalSecret.
# Allows scaffolder actions (http:backstage:request → /proxy/vault) to write
# secrets for team services at secret/teams/{team}/{service}.
path "secret/data/teams/*/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/teams/*/*" {
  capabilities = ["list", "read"]
}
