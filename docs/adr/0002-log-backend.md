# ADR 0002: Log backend (Loki vs VictoriaLogs)

**Status:** Proposed

<!-- VERDICT: UNFILLED -->

## Context

Issue #2245 asks whether VictoriaLogs would beat the current log backend on
the MCTL workload. The boundary set by the issue: the answer must come from
measuring the real workload (dual-written traffic), not from a desk study and
not from ingestion numbers alone. This ADR freezes the rubric before any
measurement exists; the live round is a separate, owner-gated change that
follows `docs/runbooks/log-backend-bake-off.md`.

Candidates:

- `loki-current`: the running `loki-stack` Application.
- `victorialogs`: single-node VictoriaLogs.

### Current state

From `platform-gitops/bootstrap/templates/observability/loki.yaml`:

- Chart `loki-stack` 2.10.2, Loki image `grafana/loki:2.9.17`, single pod,
  `persistence.enabled: false` (`/data` is emptyDir).
- Resources: requests 100m / 1Gi, limits 200m / 2048Mi.
- Storage: tsdb + s3 (schema v12, 24h index period) in the R2 bucket `loki`,
  60-day backstop lifecycle rule.
- Limits: `ingestion_rate_mb: 4`, burst 8, `retention_period: 336h`, and a
  `retention_stream` keeping `{namespace="vault", container="vault"}` for
  720h (Vault audit log, SOC 2). `max_look_back_period: 720h`.
- Promtail DaemonSet is the shipper; its custom metric counters are produced
  by Promtail and are independent of the storage backend.

### Consumers a migration would touch

- mctl-api `LOKI_URL` (`bootstrap/templates/mctl-platform/mctl-api.yaml`),
  which backs `mctl_get_service_logs` (LogQL).
- Grafana datasource `bootstrap/templates/observability/loki-datasource.yaml`
  (derived field `trace_id=` to Tempo).
- Protected-Application lists naming `loki-stack` in
  `wft-create-tenant.yaml` and `wft-delete-tenant-safe.yaml`.

## Rubric

Weights sum to 100. The same table lives in `docs/adr/0002-rubric.yaml`;
`tests/test_adr0002_rubric_frozen.py` keeps them in agreement. Cells are
scored 1-5 once measured.

| Dimension | Weight |
|---|---|
| Ingest resources | 15 |
| Storage cost | 15 |
| Query latency | 15 |
| Retention | 10 |
| Tenant isolation | 10 |
| HA and recovery | 15 |
| Consumer compatibility | 10 |
| Migration cost | 10 |

Dimensions: ingest_resources (CPU/memory of backend and shipper at the same
ingest rate), storage_cost (bytes stored per ingested GB, monthly cost of R2
vs PVC), query_latency (p50/p95 of a fixed query set at 1h/24h/7d),
retention (14d default plus 30d Vault audit stream), tenant_isolation
(per-tenant scoping and how mctl-api would enforce it), ha_recovery (pod
kill and node drain behaviour, loss window, restore path), consumer_compat
(mctl-api LogQL, Grafana datasource, derived fields, alerting) and
migration_cost (engineering and dual-run effort, LogQL to LogsQL rewrite).

## Decision rule

Recommend a change only if the VictoriaLogs weighted score exceeds Loki's by
at least 0.5 (on the 1-5 cell scale), no dimension is "not measured", and
retention and consumer_compat are each >= 3. Anything else is "keep Loki"
with the evidence recorded. No change is recommended from ingestion numbers
alone.

## Decision

No verdict recorded yet. Until the live round fills the rubric, the current
Loki deployment stays as is.

## Verdict record

Empty.
