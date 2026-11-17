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

# Explicit deny on the Glovo C2 service prefix (private keys, DB passwords, audit
# key, tailnet auth key). The platform/* grant above would let any workflow run
# as argo-workflow-sa read, overwrite and delete them, so the prefix is cut out
# here. A deny wins over the grant. It does not make argo-workflow a lesser
# identity: its sibling policy argo-workflow-provisioner can mint policies and
# roles, so the role stays platform-admin-equivalent (see the vault-config
# README, "Platform trust boundary"). The service's own role `eso-mctl-glovo` and
# `glovo-db-creds` still read it; nothing in the workflow templates touches
# this prefix (mctlhq/mctl-gitops#2759).
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
