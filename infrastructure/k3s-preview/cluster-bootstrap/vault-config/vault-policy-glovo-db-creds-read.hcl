# Database role passwords of the Glovo C2 cluster service, read by the
# `glovo-db-creds` SecretStore in the platform-db namespace
# (platform-gitops/infra-components/data/cnpg/shared/secretstore.yaml).
#
# The CNPG managed roles need these two passwords in platform-db, next to the
# Cluster, so the service's own namespaced store (mctl-glovo) cannot serve
# them. The cluster-wide `vault-backend` store denies the whole prefix
# (external-secrets-read, mctlhq/mctl-gitops#2759), so this role is the only
# way those ExternalSecrets read it. Scope: the `database-*` keys of the prefix
# (database-runtime, database-migrator) and nothing else; no control-caller,
# no signing keys, no tailnet key.
#
# platform-db hosts no tenant workloads, so nothing a tenant controls can
# authenticate as this role.
#
# Apply (README.md, "Glovo C2 ESO roles"):
#   vault policy write glovo-db-creds-read vault-policy-glovo-db-creds-read.hcl
#   vault write auth/kubernetes/role/glovo-db-creds \
#     bound_service_account_names=glovo-db-creds \
#     bound_service_account_namespaces=platform-db \
#     policies=glovo-db-creds-read \
#     ttl=1h

path "secret/data/platform/mctl-glovo/database-*" {
  capabilities = ["read"]
}

path "secret/metadata/platform/mctl-glovo/database-*" {
  capabilities = ["read", "list"]
}
