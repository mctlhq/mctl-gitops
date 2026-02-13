# Vault policies per team
# Apply after Vault is initialized and unsealed.
#
# Usage:
#   vault policy write team-developers vault-policy-developers.hcl
#   vault policy write team-control vault-policy-control.hcl
#
# To add a new team, create a file with:
#   path "secret/data/preprod/<TEAM_NAME>/*" {
#     capabilities = ["read", "list"]
#   }

# --- Team: developers ---
# File: vault-policy-developers.hcl
# path "secret/data/preprod/developers/*" {
#   capabilities = ["read", "list"]
# }

# --- Team: control ---
# File: vault-policy-control.hcl
# path "secret/data/preprod/control/*" {
#   capabilities = ["read", "list"]
# }

# --- ESO read-all policy ---
# This policy is used by the ExternalSecrets Operator service account.
# It needs read access to all team secrets.
# File: vault-policy-external-secrets-read.hcl
# path "secret/data/preprod/*" {
#   capabilities = ["read"]
# }
# path "secret/metadata/preprod/*" {
#   capabilities = ["read", "list"]
# }
