# ESO read policy for the namespaced SecretStore `mctl-api-control-vault` in the
# mctl-api namespace (platform-gitops/bootstrap/templates/mctl-platform/mctl-api-c2-control.yaml).
# Bound to the Kubernetes auth role `eso-mctl-api-control`, which only the
# dedicated ServiceAccount `mctl-api-control-eso` in namespace `mctl-api` can log
# in as. That ServiceAccount is used by ESO token requests only (automount off).
#
# Grants exactly ONE key: the control-caller credential of the C2 kill switch
# client. Not the prefix wildcard (that is eso-mctl-glovo, for the service's own
# namespace): mctl-api must not be able to read the service's signing keys,
# database passwords or tailnet key, and a compromise of this role must not
# widen to them. The cluster-wide `vault-backend` store denies the prefix, so
# this role is the only way the mctl-api namespace reads the key
# (mctlhq/mctl-gitops#2759, #2742).
#
# Apply (see README.md, "mctl-api control-caller store"):
#   vault policy write eso-mctl-api-control vault-policy-eso-mctl-api-control.hcl

path "secret/data/platform/mctl-glovo/control-caller" {
  capabilities = ["read"]
}

path "secret/metadata/platform/mctl-glovo/control-caller" {
  capabilities = ["read", "list"]
}
