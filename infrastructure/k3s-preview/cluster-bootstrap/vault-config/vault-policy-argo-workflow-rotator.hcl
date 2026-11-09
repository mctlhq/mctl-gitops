# Argo Workflows: GitHub App token rotation, and nothing else.
#
# Used only by the role argo-workflow-rotator (vault-role-argo-workflow-rotator.json),
# bound to argo-workflows/argo-workflow-rotator-sa. It carries the exact paths the
# rotate-github-app-tokens template touches (cwft-rotate-github-token.yaml:
# creds_path / dest_path) and no glob, no sys/, no teams/, no policy or role
# management. tests/test_vault_rotator_role.py derives the path set from that
# template and fails if this file grants more or less.
#
# NOT YET IN USE: the template still logs in with the role argo-workflow. Moving it
# is a separate change with its own approval.
#
# Apply (needs a separate owner GO, not done by merging this file):
#   vault policy write argo-workflow-rotator vault-policy-argo-workflow-rotator.hcl

# Source credentials: read only. Never writable from this role.
path "secret/data/platform/github-app-agents" {
  capabilities = ["read"]
}

# Destinations: read the current object, write the refreshed token back.
# No create (the objects exist), no delete, no list.
path "secret/data/platform/mctl-agent/tokens" {
  capabilities = ["read", "update"]
}

path "secret/data/platform/mctl-agents" {
  capabilities = ["read", "update"]
}

path "secret/data/platform/mctl-api/github-app" {
  capabilities = ["read", "update"]
}
