# CNPG shared-pg database credentials, read by the `cnpg-db-creds` SecretStore
# in the platform-db namespace.
#
# The per-tenant DB credential ExternalSecrets live in platform-db (next to the
# CNPG Cluster), not in the tenant namespace, so they cannot use a tenant-scoped
# store. This policy is deliberately narrower than a teams/* wildcard: the `+`
# segments match exactly one level each, so it grants the `database` key of every
# team's services and nothing else — no repo-pat, no telegram, no api tokens.
#
# platform-db hosts no tenant workloads, so nothing a tenant controls can
# authenticate as this role.
#
# Apply:
#   vault policy write cnpg-db-creds-read vault-policy-cnpg-db-creds-read.hcl
#   vault write auth/kubernetes/role/cnpg-db-creds \
#     bound_service_account_names=cnpg-db-creds \
#     bound_service_account_namespaces=platform-db \
#     policies=cnpg-db-creds-read \
#     ttl=1h

path "secret/data/teams/+/+/database" {
  capabilities = ["read"]
}

path "secret/metadata/teams/+/+/database" {
  capabilities = ["read", "list"]
}

# Read-only shared-pg roles that are not the service's own `database` key —
# currently only academy_readonly (Grafana dashboards against mctl-academy).
# Add a path here when another read-only pg role is provisioned; do NOT widen
# the patterns above to teams/+/+/* , which would pull in repo-pat and telegram.
path "secret/data/teams/+/+/grafana-readonly" {
  capabilities = ["read"]
}

path "secret/metadata/teams/+/+/grafana-readonly" {
  capabilities = ["read", "list"]
}
