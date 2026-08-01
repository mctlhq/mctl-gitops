# Backstage: read/write team secrets.
#
# Covers secret/teams/{team}/{service} and sub-paths like
# secret/teams/{team}/{service}/database, /repo-pat and /telegram — the paths
# wft-provision-database.yaml and tpl-vault-write.yaml write and
# vault-secrets-backend reads back.
#
# Note: '+' is a single-segment wildcard; '*' is a glob only at end of path.
path "secret/data/teams/+/+" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/data/teams/+/+/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/teams/+/+" {
  capabilities = ["list", "read"]
}

path "secret/metadata/teams/+/+/*" {
  capabilities = ["list", "read"]
}

# NOTE: there is deliberately no secret/*/platform/teams/... grant here.
# It existed only because vault-secrets-backend read DB credentials from
# platform/teams/{team}/{app}/database, a prefix nothing has ever written
# (mctl-portal#51 fixed the reader). Confirmed dead before removal: nothing in
# either repo references the prefix, and LIST secret/metadata/platform/teams
# on the live cluster returns no keys. Provisioning uses its own policy,
# argo-workflow-teams-rw.
