# ESO read policy for the namespaced SecretStore `mctl-glovo-vault` in the
# mctl-glovo namespace (platform-gitops/bootstrap/templates/mctl-platform/mctl-glovo.yaml).
# Bound to the Kubernetes auth role `eso-mctl-glovo`, which only the dedicated
# ServiceAccount `mctl-glovo-eso` in namespace `mctl-glovo` can log in as.
#
# Grants exactly the service's own prefix and nothing else. The cluster-wide
# `vault-backend` store (external-secrets-read) denies this prefix, so after
# the switch the keys under it are readable only through this role
# (mctlhq/mctl-gitops#2759).
#
# Apply (see README.md, "Glovo C2 ESO role", for the order):
#   vault policy write eso-mctl-glovo vault-policy-eso-mctl-glovo.hcl

path "secret/data/platform/mctl-glovo/*" {
  capabilities = ["read"]
}

path "secret/metadata/platform/mctl-glovo/*" {
  capabilities = ["read", "list"]
}
