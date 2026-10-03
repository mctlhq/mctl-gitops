# Investigate sharp drop in tenant `admins` resource-usage metrics

## Context
Tenant `admins` — where mctl-portal itself runs — showed CPU-limit usage fall from
~67.5% to 16.5% and memory-limit usage fall from ~65% to ~30.7% between the
2026-09-19 and 2026-09-26 cycles, with quota unchanged (10 CPU / 5Gi mem limits) and
pod count essentially unchanged (7 of 12 pods, matching the prior three cycles).
Requests-side usage (300m CPU / 704Mi mem) and PVC/service counts show no obvious
compensating change. No ArgoCD status change (still `Healthy`/`Synced`, revision
`2.6.3` unchanged for four consecutive cycles) and no open incidents accompany this
delta, so there is no corroborating signal yet pointing to a specific cause.

This is a metrics-observation-only finding, not a confirmed root cause. A drop this
large, with the same pod count, could be benign (e.g., a workload rightsizing,
horizontal pod autoscaling settling to a lower steady state, or a one-off spike in
the prior three cycles now resolved) or it could be a symptom of a problem: a silent
crash-loop/restart cycle depressing average usage, a container failing to start at
its expected resource footprint, or — notably — a break in the same metrics pipeline
already implicated by the open `proposals/portal-log-pipeline-gap/` proposal (service
logs have returned 0 lines for four consecutive cycles). Because both anomalies are
metrics-integrity issues on the same service/tenant and appeared in overlapping
windows, they may share a root cause and should be investigated with that
possibility explicitly in mind, without assuming it up front.

## User stories
- AS a platform operator I WANT to know why tenant `admins` resource-usage figures
  dropped so sharply in one cycle SO THAT I can distinguish a legitimate workload
  change from a masked incident before it affects capacity planning or hides a real
  problem.
- AS an on-call engineer I WANT confidence that the metrics pipeline reporting
  tenant `admins` usage is accurate SO THAT I can trust it during an actual incident
  instead of discovering a blind spot under pressure.
- AS the mctl-portal owner I WANT to know whether this anomaly shares a root cause
  with the already-open `portal-log-pipeline-gap` investigation SO THAT the two are
  fixed together rather than duplicating diagnostic effort.

## Acceptance criteria (EARS)
- WHEN this investigation is performed THE SYSTEM SHALL produce a documented root
  cause classification for the resource-usage drop: (a) legitimate workload/scaling
  change, (b) silent pod crash-loop/restart pattern depressing observed usage, (c) a
  metrics-collection/reporting pipeline defect (e.g., stale or partial scrape), or
  (d) another cause, with supporting evidence for the chosen classification.
- WHEN the per-pod state of tenant `admins` workloads is inspected THE SYSTEM SHALL
  record pod restart counts, container states, and per-pod resource usage for the
  affected window, to rule in or out a crash-loop explanation.
- WHEN the investigation checks the metrics pipeline THE SYSTEM SHALL compare the
  tenant-level usage figures against an independent source (e.g., raw
  Prometheus/kube-state-metrics query for the `admins` namespace) to confirm or
  refute a reporting-layer discrepancy, and SHALL explicitly note whether this
  overlaps with the root cause of `portal-log-pipeline-gap`.
- IF the root cause is classified as a legitimate workload change THEN THE SYSTEM
  SHALL document the change (what shrank, why) so capacity planning is not surprised
  by it in a future cycle, and no further remediation is required under this
  proposal.
- IF the root cause is classified as a crash-loop, restart pattern, or other service
  health defect THEN THE SYSTEM SHALL flag it as a service-health issue for the
  mctl-portal owner to remediate, and this proposal SHALL be updated (or a follow-on
  proposal opened) to track the fix — the fix itself is out of scope here.
- IF the root cause is classified as a metrics-pipeline defect THEN THE SYSTEM SHALL
  cross-reference `proposals/portal-log-pipeline-gap/` and, if a shared root cause is
  confirmed, THE SYSTEM SHALL consolidate follow-up remediation into a single
  tracked effort rather than two parallel fixes.
- WHILE the investigation is in progress THE SYSTEM SHALL NOT trigger any scaling,
  restart, or configuration change against tenant `admins` workloads without an
  explicit instruction, since this proposal is diagnostic-only.

## Out of scope
- Any fix to tenant `admins` workload scaling, pod configuration, or quotas — this
  proposal only establishes the root cause; remediation is tracked separately once
  known.
- Tenant `labs` — its quota/usage change this cycle is unrelated (a quota increase
  that eased prior near-saturation) and is not part of this investigation.
- Re-diagnosing the empty-service-logs symptom from scratch — that is owned by
  `proposals/portal-log-pipeline-gap/`; this proposal only checks for a shared root
  cause and cross-references that proposal's findings rather than duplicating its
  investigation steps.
- Building a permanent anomaly-detection/alerting system for tenant resource usage —
  a one-time root-cause investigation, not a new monitoring capability.
