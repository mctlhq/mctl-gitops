# Backstage: read/write team secrets (for scaffolder templates)
# Used by the VAULT_TOKEN injected into Backstage via backstage-secrets ExternalSecret.
# Allows scaffolder actions (http:backstage:request → /proxy/vault) to write
# secrets for team services at secret/teams/{team}/{service} and sub-paths
# like secret/teams/{team}/{service}/repo-pat.
#
# Note: '+' is a single-segment wildcard; '*' is a glob only at end of path.
path "secret/data/teams/+/+" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/data/teams/+/+/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/teams/+/+" {
  capabilities = ["list", "read"]
}

path "secret/metadata/teams/+/+/*" {
  capabilities = ["list", "read"]
}

# Platform team secrets — for provisioning workflow
path "secret/data/platform/teams/+/+" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/data/platform/teams/+/+/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/platform/teams/+/+" {
  capabilities = ["list", "read"]
}

path "secret/metadata/platform/teams/+/+/*" {
  capabilities = ["list", "read"]
}
