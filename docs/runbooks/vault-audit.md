# Vault audit log (secrets.mctl.ai)

Every request Vault serves, and every response, is written as one JSON entry
by the audit device at path `stdout` (type `file`, `file_path=stdout`). The
entries go to the vault container's stdout, Promtail ships them to Loki with
the rest of the pod logs, and Grafana's Loki datasource queries them.

| Piece | Where |
| --- | --- |
| The device (`vault_audit.stdout`) | `platform-gitops/helm-charts/vault-human-auth-iac/iac/audit.tf` |
| The Job's grant on `sys/audit` (applied by hand) | `infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-vault-human-auth-iac.hcl` |
| Counters `vault_audit_entries_total`, `vault_audit_failures_total` | Promtail match block in `platform-gitops/bootstrap/templates/observability/loki.yaml` |
| Alerts `VaultAuditLogSilent`, `VaultAuditLogAbsent`, `VaultAuditWriteFailures` | `platform-gitops/infra-components/observability/vm-rules/vault-audit-alerts.yaml` (routed to Telegram) |
| Retention | Loki `limits_config.retention_stream` 720h (30 days) for `{namespace="vault", container="vault"}`, other streams `retention_period` 336h; same file as the Promtail block |

## What is in an entry, and what is not

- `type` is `request` or `response`. Each request produces one of each, sharing
  `request.id`. Requests Vault refuses (403, 400) are logged too, with `error`.
- `auth`: who acted. `display_name`, `entity_id`, `policies`, `metadata`, and
  HMAC'd `client_token` and `accessor`.
  - Humans (OIDC, `auth/mctl`): `display_name` is `mctl-<ZITADEL user id>`,
    `metadata.email` and `metadata.username` come from the token's claims
    (`claim_mappings` in `vault-human-auth-iac/iac/oidc.tf`).
  - Workloads (`auth/kubernetes`): `metadata.service_account_namespace`,
    `metadata.service_account_name` and `metadata.role`.
- `request`: `path`, `operation` (`read`, `list`, `create`, `update`,
  `delete`), `remote_address`, `mount_point`.
- Secret values, tokens and accessors are HMAC'd (`hmac-sha256:...`) with a
  key only this Vault holds. The log shows that `secret/data/teams/x/db` was
  read and by whom, never the value. `log_raw` is never set: anyone with
  Grafana can query this log.
- Only the active node writes entries; standbys forward requests to it. After
  a leader change the entries continue on another `vault-N` pod.
- `sys/health`, `sys/seal-status` and the other unauthenticated status
  endpoints are not audited, so the readiness probes and the auto-unseal
  CronJob add nothing.

## Querying it (Grafana, Explore, datasource Loki)

The stream selector for every query:

```logql
{namespace="vault", container="vault", stream="stdout"}
```

`| json` flattens nested keys with `_`: `auth.metadata.email` becomes
`auth_metadata_email`, `request.path` becomes `request_path`. Put a line
filter (`|=`) before `| json`; it is much cheaper than parsing every entry.

**Who read a given secret** (KV v2: the path carries `data/`):

```logql
{namespace="vault", container="vault", stream="stdout"}
  |= "secret/data/teams/erpact/"
  | json
  | type = "response" and request_operation = "read"
  | request_path =~ "secret/data/teams/erpact/.*"
  | line_format "{{.time}} {{.request_path}} by {{.auth_display_name}} {{.auth_metadata_email}}{{.auth_metadata_service_account_namespace}}/{{.auth_metadata_service_account_name}} from {{.request_remote_address}} {{.error}}"
```

**Who changed a secret or a policy**: the same query with
`request_operation =~ "create|update|patch|delete"`, or the prefix
`sys/policies/acl/` instead of a secret path.

**Everything one person did**, by e-mail (humans) or by entity id (stable
across logins and renames; `vault read identity/entity/name/<name>` or the UI
gives it):

```logql
{namespace="vault", container="vault", stream="stdout"}
  |= "someone@example.com"
  | json
  | type = "response" and auth_metadata_email = "someone@example.com"
  | line_format "{{.time}} {{.request_operation}} {{.request_path}} {{.error}}"
```

```logql
{namespace="vault", container="vault", stream="stdout"}
  |= "<entity id>"
  | json
  | type = "response" and auth_entity_id = "<entity id>"
  | line_format "{{.time}} {{.request_operation}} {{.request_path}} {{.error}}"
```

**Everything one workload did**:

```logql
{namespace="vault", container="vault", stream="stdout"}
  |= "service_account_namespace\":\"erpact\""
  | json
  | type = "response"
  | line_format "{{.time}} {{.auth_metadata_service_account_name}} {{.request_operation}} {{.request_path}} {{.error}}"
```

**Refusals** (`permission denied` and other errors):

```logql
{namespace="vault", container="vault", stream="stdout"}
  |= "\"error\":"
  | json
  | type = "response"
  | line_format "{{.time}} {{.auth_display_name}} {{.request_operation}} {{.request_path}}: {{.error}}"
```

**One token's entries.** The log carries the HMAC of the token's accessor, not
the accessor. Compute it with an admin token, then filter on the result:

```bash
vault write -field=hash sys/audit-hash/stdout input=<accessor>
# hmac-sha256:...  ->  |= "hmac-sha256:..."
```

`sys/audit-hash` hashes with this device's key; the hash differs per device
and per Vault cluster, so a hash from a restored or rebuilt Vault does not
match old entries.

**Volume**: `sum(count_over_time({namespace="vault", container="vault",
stream="stdout"} [1h]))`, and `bytes_over_time(...)` for size.

## Volume and retention

Measured before enablement (2026-10-04, `sys/metrics` on the active node):
about 0.4 requests a second, with logins about one in six. ESO refreshes
alone account for ~0.13 reads a second (169 ExternalSecrets, mostly hourly).
That is ~35,000 requests and ~70,000 entries a day; at ~1.5-2 KB an entry,
roughly 100-150 MB a day of raw lines before Loki's compression, and well
under Loki's 4 MB/s ingestion limit. Re-measure with the volume query above a
day after enablement and correct this paragraph.

Loki keeps the Vault container streams (stdout audit entries and the stderr
server log with any `failed to audit` lines) for 30 days through
`limits_config.retention_stream`; every other stream stays at the global 336h.
30 days is an owner-accepted decision of 2026-10-04 (mctl-gitops#1659): shorter
than the 90 days to a year an auditor may ask for, accepted against the
storage cost. `chunk_store_config.max_look_back_period` is 720h to match, so the
whole 30 days stays queryable. Chunks live in the R2 bucket `loki`, whose
dashboard-managed lifecycle rule `backstop-expire-after-60-days` deletes objects
after 60 days; it is a backstop behind the compactor and must stay longer than
every Loki retention, or R2 deletes chunks Loki still indexes. Raising Vault
retention past 60 days means raising that rule first.

Loki restarts on any config change. The ingester WAL is on an emptyDir, so
`ingester.wal.flush_on_shutdown: true` flushes in-memory chunks to R2 on a
graceful stop instead of dropping up to two hours of logs, audit lines included.

## One device, and what happens when it fails

Vault refuses any request it could not write to at least one audit device. In
1.17 each entry gets 5 seconds; after that the request fails with `500
internal error`, and Vault logs `core: failed to audit request` or `core:
failed to audit response` on stderr. That includes `vault audit disable`
itself: once every device fails, the API cannot remove the device
(reproduced on a local 1.17.2 with a socket device whose listener was killed).

There is one device, `stdout`. A second device would only help if it could
keep working while stdout does not, and none of the candidates is worth it:

- **A file on the Raft volume** (`/vault/data`, 1 GiB): nothing rotates it, and
  at ~100+ MB a day it fills the volume Raft lives on within two weeks. That
  outage is worse than the one it guards against.
- **A dedicated audit volume** (`server.auditStorage`): a new
  volumeClaimTemplate, which a StatefulSet cannot take in place (delete and
  recreate the StatefulSet), three more paid Hetzner volumes, and still no
  rotation.
- **A socket device to a collector** (otel-collector, Promtail): a network
  dependency that fails more often than stdout does. A slow socket also holds
  every request for up to the 5-second timeout even while stdout succeeds.
- **syslog**: no syslog daemon in the pod.

stdout itself fails in two ways, and neither leaves Vault wedged for long:

- **The pipe breaks** (the containerd shim dies): Go exits on a broken pipe on
  fd 1, the pod restarts, and a standby takes the lead in the meantime.
- **The pipe stops draining** (the shim hangs, the node's disk is full): writes
  block, entries time out, requests on that node fail.
  `VaultAuditWriteFailures` fires. Delete the active pod
  (`kubectl -n vault get pods -l vault-active=true`); a standby on another
  node takes the lead with its own stdout, and the audit table (replicated in
  Raft) re-opens the device there. Unseal the restarted pod as usual
  (vault-auto-unseal runs every two minutes).

## Operations

- **The device is missing** (`vault audit list` shows no `stdout/`):
  `VaultAuditLogSilent` fires. The vault-human-auth-iac CronJob re-enables it at
  :37, or at once on a sync of the Application. Disabling it needs `sudo` on
  `sys/audit/stdout` with `delete`, which only the owner's `admin` policy holds;
  find who did it in the entries just before the gap
  (`|= "sys/audit/stdout"`).
- **Changing the device** (options, description): every field is ForceNew, so
  the plan is a replace. The Job refuses it (no `delete` in its plan guard for
  this address, and no `delete` in its Vault policy). The owner disables the
  device with an admin token, the Job re-creates it from the new config, and
  the gap between the two is unaudited; keep it short.
- **Checking the pipeline**: `vault audit list -detailed` on any pod; the
  query above returns entries from the last minute; `vault_audit_entries_total`
  rises in VictoriaMetrics.

## Bootstrap (2026-10, owner)

The Job's Vault policy needs two more paths before the Job can enable the
device. Apply the updated policy with an admin token **before** the PR that adds
`audit.tf` merges; until then the Job's plan includes the device and its apply
fails with 403, while everything else it manages stays as it is:

```bash
vault policy write vault-human-auth-iac \
  infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-vault-human-auth-iac.hcl
```

Check: `vault policy read vault-human-auth-iac` ends with the `sys/audit` and
`sys/audit/stdout` paths. After the merge, the PostSync Job applies
`vault_audit.stdout` (plan: 1 to add), and `vault audit list` shows `stdout/`.

**Rollback:** the owner runs `vault audit disable stdout`, then reverts the PR
(otherwise the Job re-enables it within the hour).
