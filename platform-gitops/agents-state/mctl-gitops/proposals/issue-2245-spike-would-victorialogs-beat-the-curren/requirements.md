# Spike: measured VictoriaLogs vs current Loki comparison on the mctl log workload

## Context

Issue #2245 (scout-generated) asks whether VictoriaLogs would beat the current
log backend on ingestion cost and resource use for multi-tenant structured
logs on mctl clusters. The trigger is a VictoriaMetrics vendor benchmark. The
issue's own boundary is explicit: the vendor numbers are a hypothesis, not the
decision. The comparison must be reproduced on the real MCTL log workload
against the real backend, and must also cover query latency, retention and
storage behaviour, tenant isolation, HA/recovery and the cost of migrating.
No backend change may be recommended from single-node ingestion numbers.

Today the backend is the `loki-stack` Application
(`platform-gitops/bootstrap/templates/observability/loki.yaml`): chart
`loki-stack` 2.10.2, Loki pinned to 2.9.17, one single-binary pod with tsdb
index and chunks in the Cloudflare R2 bucket `loki`, WAL on emptyDir, 14d
default retention and a 30d `retention_stream` for the Vault audit log
(SOC 2, #1659), fed by a Promtail DaemonSet that also runs metrics stages
whose counters back VMRules. Log storage is a real cost on a three-worker
cx43 cluster, so a measured answer is worth having; a wrong migration would
put the Vault audit evidence, `mctl_get_service_logs` (mctl-api `LOKI_URL`)
and Grafana's Loki<->Tempo links at risk. This proposal follows the pattern
the trace-backend spike used (ADR 0001, issue #903 offline half, #1280 live
half): a frozen rubric and a gated, time-boxed sandbox committed first, then
an owner-gated live round that fills the rubric from measurements.

## User stories

- AS a platform owner I WANT a cited, measured comparison of VictoriaLogs and
  the running Loki on our own log stream SO THAT a backend decision rests on
  mctl evidence rather than a vendor benchmark.
- AS a platform operator I WANT the evaluation sandbox to be off by default,
  quota-bounded and forced to expire SO THAT a spike cannot silently become
  permanent or starve tenant workloads.
- AS an operator relying on logs today I WANT production Loki ingestion,
  retention and queries unaffected by the spike SO THAT incident evidence and
  the Vault audit trail stay complete during the evaluation.
- AS a reviewer I WANT the scoring rubric and decision rule frozen before any
  score exists SO THAT the result cannot be retrofitted to a favourite.

## Acceptance criteria (EARS)

- WHEN the implementer change merges THE SYSTEM SHALL contain
  `docs/adr/0002-log-backend.md` (status Proposed) and
  `docs/adr/0002-rubric.yaml` whose dimensions cover at least: ingestion
  resource use (CPU, memory), storage footprint and cost per retained GB,
  representative query latency, retention behaviour (including the 30d Vault
  audit stream), tenant isolation, HA/recovery, consumer compatibility
  (mctl-api, Grafana, derived fields) and migration cost.
- WHEN the rubric file is committed THE SYSTEM SHALL have every candidate
  score null and a CI test SHALL fail if any score is filled while the ADR
  verdict is not recorded, or if rubric weights disagree with the ADR table.
- WHILE `logsEval.enabled` in `platform-gitops/bootstrap/values.yaml` is
  false THE SYSTEM SHALL render no namespace, Application, NetworkPolicy,
  scrape object, datasource or Promtail client for the evaluation, so the
  rendered production manifests are byte-identical to today's.
- IF `logsEval.enabled` is true AND `logsEval.teardownAfter` is empty,
  unparseable, in the past or more than 14 days ahead THEN THE SYSTEM SHALL
  fail `validate-manifests.yml`.
- WHILE the sandbox is open THE SYSTEM SHALL bound the candidate by a
  ResourceQuota and LimitRange in its own namespace and a default-deny
  NetworkPolicy that admits only Promtail (push), vmagent (scrape) and
  Grafana (query).
- WHILE the sandbox is open THE SYSTEM SHALL keep the existing Loki client
  first and unchanged in Promtail's `clients` list, and the candidate client
  SHALL be bounded (finite retries, finite batch wait) so a candidate outage
  cannot stall delivery to Loki.
- WHEN the live round runs THE SYSTEM SHALL measure both backends over the
  same window on the same Promtail-fed stream, from VictoriaMetrics series
  and repeatable query scripts, and record each rubric cell as a cited score
  or a cited "not measured".
- IF a dimension was not measured THEN THE ADR SHALL NOT recommend a backend
  change on the basis of the remaining dimensions alone.
- WHEN the round ends THE SYSTEM SHALL return `logsEval.enabled` to false and
  ArgoCD SHALL prune the sandbox, leaving `loki-stack` as it was.

## Out of scope

- Replacing, reconfiguring or upgrading the production `loki-stack`
  Application (including Loki 2.9 -> 3.x).
- Migrating any consumer (mctl-api `LOKI_URL`, Grafana datasource, Promtail
  metrics stages, VMRules) to VictoriaLogs. A positive verdict opens a
  separate migration proposal.
- Moving logs into the OpenTelemetry Collector (that is #2211's territory).
- A VictoriaLogs cluster-mode or HA deployment in this round; HA/recovery is
  assessed from a single-node outage test plus documented behaviour.
- New nodes or new paid storage beyond one small, quota-capped PVC.

## Open questions

- Candidate pin: the chart repository, chart name and version of the
  VictoriaLogs single-node chart, and the VictoriaLogs image version, could
  not be verified offline. The live round must fill them from the upstream
  `index.yaml` and record the date checked; the offline change commits the
  candidate entry with empty pins and `enabled: false`.
- Storage model mismatch: Loki here keeps data in R2 with no PVC; VictoriaLogs
  single-node stores on a local filesystem. Is one 10-20Gi Hetzner volume for
  the sandbox acceptable to the owner? Assumed yes (it is deleted at
  teardown); otherwise the round must use emptyDir and cannot test recovery.
- Per-stream retention: Loki keeps the Vault audit stream 30d and the rest
  14d. Whether VictoriaLogs can express that inside one instance (versus a
  second tenant/instance) must be established in the live round and scored
  under retention.
- Tenant isolation baseline: `loki.yaml` does not set `auth_enabled`, so the
  running Loki uses the chart default; the live round must confirm whether
  production Loki is single-org today (isolation by `namespace` label in
  mctl-api queries) before comparing it with VictoriaLogs AccountID/ProjectID.
- Rubric weights: proposed in design.md; the owner may change them before the
  live round, but not after any score exists.
- Whether the mctl-agents scout should also file the follow-up live-round
  issue, or the owner opens it (as #1280 was for #903).
