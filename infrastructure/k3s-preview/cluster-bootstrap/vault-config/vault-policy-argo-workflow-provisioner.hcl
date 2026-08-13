# Argo Workflows: tenant provisioning (admin-only operations)
# Used ONLY by wft-create-tenant and wft-delete-tenant workflows.
# Allows creating per-tenant Vault policies.
#
# SECURITY: This policy should be bound to a dedicated ServiceAccount
# (e.g. argo-workflow-provisioner-sa) in a future iteration.
# Currently bound to argo-workflow-sa alongside argo-workflow-teams-rw.
#
# Apply:
#   vault policy write argo-workflow-provisioner vault-policy-argo-workflow-provisioner.hcl

# Create/manage per-tenant Vault policies
# Naming convention: tenant-{name}
path "sys/policies/acl/tenant-*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Per-tenant ESO policies, read by the namespaced SecretStore in each tenant
# namespace. Kept separate from tenant-{name} (which scopes Argo's own
# read/write access) so the two can diverge without widening either.
path "sys/policies/acl/eso-tenant-*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Kubernetes auth roles backing those ESO policies. Without this, the tenant
# policy created by wft-create-tenant stays an orphan ACL that nothing can assume.
path "auth/kubernetes/role/eso-tenant-*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Read own policy (for debugging/verification)
path "sys/policies/acl/argo-workflow-provisioner" {
  capabilities = ["read"]
}

path "sys/policies/acl/argo-workflow-teams-rw" {
  capabilities = ["read"]
}
