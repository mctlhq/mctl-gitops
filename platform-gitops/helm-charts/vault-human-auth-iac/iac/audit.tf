# Vault's audit log: one `file` device writing JSON lines to the server's
# stdout. Promtail ships the vault pods' container logs to Loki, so every
# request and response lands there as {namespace="vault", container="vault",
# stream="stdout"}. Runbook (queries, failure modes):
# docs/runbooks/vault-audit.md.
#
# Here and not in a root of its own because it is one resource, and this root
# already runs as the Job that configures Vault's own access surface, which is
# what the audit log records; a second Job would be a second namespace,
# ServiceAccount, Kubernetes auth role and state for the same resource.
#
# Defaults kept on purpose. Secret values, tokens and accessors are HMAC'd
# (hmac_accessor defaults to true), and log_raw is never set: the log goes to
# Loki, which every Grafana viewer can query. To find a given token's lines,
# hash its accessor with `vault write sys/audit-hash/stdout input=...`.
#
# One device only. Vault refuses a request it could not audit to at least one
# device (a 5-second timeout per entry), so a second device would buy
# availability only if it failed independently of stdout; the candidates do
# not, or cost more than they save (the runbook weighs them). Every field is
# ForceNew and the Job holds no delete on sys/audit/*: changing this device is
# a destroy that the owner performs, never the Job.
resource "vault_audit" "stdout" {
  type        = "file"
  path        = "stdout"
  description = "JSON audit log to the server's stdout, shipped to Loki (vault-human-auth-iac)"

  options = {
    file_path = "stdout"
  }
}
