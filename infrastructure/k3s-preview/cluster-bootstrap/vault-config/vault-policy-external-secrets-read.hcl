# Read platform infrastructure secrets (ArgoCD, Backstage, Vault)
path "secret/data/platform/*" {
  capabilities = ["read"]
}

path "secret/metadata/platform/*" {
  capabilities = ["read", "list"]
}

# Read team application secrets
path "secret/data/teams/*" {
  capabilities = ["read"]
}

path "secret/metadata/teams/*" {
  capabilities = ["read", "list"]
}
