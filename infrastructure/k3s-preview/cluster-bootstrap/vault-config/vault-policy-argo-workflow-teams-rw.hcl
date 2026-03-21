# Argo Workflows: read/write team secrets
# Used by regular CI/CD workflows (deploy-service, provision-database, smoke-test).
# Does NOT include sys/policies — cannot create or modify Vault policies.
#
# Apply:
#   vault policy write argo-workflow-teams-rw vault-policy-argo-workflow-teams-rw.hcl

# Read/write team service secrets
path "secret/data/teams/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/teams/*" {
  capabilities = ["read", "list", "delete"]
}

# Read/write platform secrets (system components)
path "secret/data/platform/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/platform/*" {
  capabilities = ["read", "list", "delete"]
}
