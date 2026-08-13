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

# Three platform-operated secrets that still live under a teams/ prefix and are
# read into platform namespaces through the cluster store:
#   teams/labs/mctl-rules                    <- backstage-oauth (mctl-portal)
#   teams/labs/mctl-academy/grafana-readonly <- academy dashboard (monitoring)
#   teams/admins/victoria-backup             <- Victoria backup (monitoring)
#
# Granted by exact path, never as a teams/* wildcard: the cluster store is
# usable from every namespace, so a wildcard here is what let any tenant read
# any other tenant's secrets. Naming them individually keeps the residual
# exposure to these three objects.
#
# Each is really a platform secret filed under the wrong prefix. Moving them to
# secret/platform/... and deleting these three entries is the proper cleanup;
# it needs a Vault data migration plus an update to each consumer, so it is
# deliberately not bundled with this change.
path "secret/data/teams/labs/mctl-rules" {
  capabilities = ["read"]
}

path "secret/data/teams/labs/mctl-academy/grafana-readonly" {
  capabilities = ["read"]
}

path "secret/data/teams/admins/victoria-backup" {
  capabilities = ["read"]
}
