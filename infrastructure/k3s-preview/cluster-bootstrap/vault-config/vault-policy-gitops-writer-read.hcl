# Read-only access to the dedicated writer path, for the identity that serves
# it through a namespaced SecretStore. Nothing else is granted.
#
# The path sits outside platform/* and teams/*, so none of the existing
# policies match it; external-secrets-read and argo-workflow-teams-rw carry an
# explicit deny on the prefix as well.
#
# Apply (owner, see README.md in this directory):
#   vault policy write gitops-writer-read vault-policy-gitops-writer-read.hcl

path "secret/data/writers/gitops/*" {
  capabilities = ["read"]
}

path "secret/metadata/writers/gitops/*" {
  capabilities = ["read", "list"]
}
