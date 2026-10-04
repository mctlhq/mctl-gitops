# GitHub Actions (mctl-gitops/.github/workflows/erpact-images.yaml, on main).
# Read-only access to the one secret that workflow uses: the Forgejo bot's
# source token (read:repository) and registry token (write:package) for the
# erpact org. Nothing else in secret/platform/*.
#
# Apply:
#   vault policy write github-actions-erpact-images \
#     infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-github-actions-erpact-images.hcl
path "secret/data/platform/forgejo/erpact-images" {
  capabilities = ["read"]
}
