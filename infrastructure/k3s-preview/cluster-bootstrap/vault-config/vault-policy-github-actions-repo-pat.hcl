# GitHub Actions (mctl-gitops/.github/workflows/build-image.yaml).
# Read-only access to the optional per-service repo PAT used as Tier 1
# checkout/push credential. Nothing else in secret/teams/* or platform/*.
#
# Apply:
#   vault policy write github-actions-repo-pat \
#     infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-github-actions-repo-pat.hcl
path "secret/data/teams/+/+/repo-pat" {
  capabilities = ["read"]
}

path "secret/metadata/teams/+/+/repo-pat" {
  capabilities = ["read"]
}
