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

# Read platform infrastructure secrets (ArgoCD, Backstage, Vault, GHCR, R2)
path "secret/data/platform/*" {
  capabilities = ["read"]
}

path "secret/metadata/platform/*" {
  capabilities = ["read", "list"]
}

# Explicit deny, so a broad platform/* grant never reaches the GitHub App
# signing key. Nothing reads it through this store: the rotation CronWorkflow
# reads it under its own Vault role. A deny wins over any read grant above.
# The glob also covers the throwaway canary path used to prove the rule.
# Keep this narrow: `platform/github-app` (no suffix) is a different secret and
# stays readable here.
path "secret/data/platform/github-app-agents*" {
  capabilities = ["deny"]
}

path "secret/metadata/platform/github-app-agents*" {
  capabilities = ["deny"]
}

# Explicit deny on the Glovo C2 service prefix (private keys, DB passwords, audit
# key, tailnet auth key). This store is usable from every namespace, so anything
# it can read is readable from any of them. The service reads its keys through
# its own namespaced SecretStore `mctl-glovo-vault` and Vault role
# `eso-mctl-glovo` (vault-policy-eso-mctl-glovo.hcl); the database role
# passwords synced in platform-db use the store `glovo-db-creds` and role
# `glovo-db-creds` (vault-policy-glovo-db-creds-read.hcl). A deny wins over the
# platform/* grant above. Apply this only AFTER both stores are live and every
# ExternalSecret reading the prefix is Ready through them (README.md, "Glovo C2
# ESO roles"), or they lose access. tests/test_no_glovo_prefix_on_vault_backend.py
# keeps any ExternalSecret in this repo from reading the prefix through a
# ClusterSecretStore.
path "secret/data/platform/mctl-glovo*" {
  capabilities = ["deny"]
}

path "secret/metadata/platform/mctl-glovo*" {
  capabilities = ["deny"]
}

# Explicit deny on the dedicated writer prefix. A deny wins over any grant, so
# a later broadening of a neighbouring glob cannot reach it. Served only by the
# gitops-writer-read policy.
path "secret/data/writers/*" {
  capabilities = ["deny"]
}

path "secret/metadata/writers/*" {
  capabilities = ["deny"]
}
