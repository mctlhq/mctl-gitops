# Backstage: read/write team secrets (for scaffolder templates)
# Used by the VAULT_TOKEN injected into Backstage via backstage-secrets ExternalSecret.
# Allows scaffolder actions (http:backstage:request → /proxy/vault) to write
# secrets for team services at secret/teams/{team}/{service} and sub-paths
# like secret/teams/{team}/{service}/repo-pat.
path "secret/data/teams/*/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/data/teams/*/*/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/teams/*/*" {
  capabilities = ["list", "read"]
}

path "secret/metadata/teams/*/*/*" {
  capabilities = ["list", "read"]
}
