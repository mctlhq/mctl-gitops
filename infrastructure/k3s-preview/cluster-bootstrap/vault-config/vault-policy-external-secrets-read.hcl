# Platform-only ESO identity, bound to the `external-secrets` Kubernetes auth role
# used by the cluster-wide `vault-backend` ClusterSecretStore.
#
# This policy deliberately grants NO access to secret/{data,metadata}/teams/*.
# The ClusterSecretStore authenticates as the ESO controller's own ServiceAccount
# and is usable from every namespace, so any tenant path readable here is readable
# by every other tenant. Tenant paths are served instead by namespaced SecretStores,
# each bound to its own `eso-tenant-{name}` role (see vault-policy-tenant-eso.hcl.tmpl).
#
# Apply:
#   vault policy write external-secrets-read vault-policy-external-secrets-read.hcl

# Read platform infrastructure secrets (ArgoCD, Backstage, Vault, GHCR, MinIO/R2)
path "secret/data/platform/*" {
  capabilities = ["read"]
}

path "secret/metadata/platform/*" {
  capabilities = ["read", "list"]
}
