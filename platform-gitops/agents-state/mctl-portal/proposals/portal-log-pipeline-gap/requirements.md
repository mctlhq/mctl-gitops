# Investigate zero-log-line gap in mctl-portal observability pipeline

## Context
`mctl_get_service_logs` has returned 0 lines for mctl-portal for at least two
consecutive daily cycles (2026-09-05 and 2026-09-12), while the ArgoCD status for the
same period reports Healthy/Synced with no open incidents. The mctl-portal
architecture relies on a Prometheus/Loki/Grafana observability stack, surfaced inside
the portal itself via the custom `observability` plugin. A sustained zero-line result
is inconsistent with a Healthy service presumably serving traffic, and suggests a
break somewhere in the log-shipping path (application log level, shipper/agent
config, or the query scope used by `mctl_get_service_logs` itself) rather than an
actual absence of logs.

This is an observability gap, not yet a confirmed incident: if it is real, on-call
has no log visibility into mctl-portal during an actual incident, undermining the
investment described in the architecture. The first goal is diagnosis; a concrete fix
follows once the root cause is known.

## User stories
- AS an on-call engineer I WANT `mctl_get_service_logs` (and the underlying
  Loki/Grafana pipeline) to return real log lines for mctl-portal SO THAT I can
  diagnose incidents without needing to shell into pods manually.
- AS a platform operator I WANT to know whether the zero-line result reflects a
  broken pipeline or a benign query/config mismatch SO THAT I can prioritize a fix
  correctly instead of assuming logging works.

## Acceptance criteria (EARS)
- WHEN an engineer runs `mctl_get_service_logs` for mctl-portal in `admins` over a
  window with known traffic (e.g., a manual login or scaffolder request) THE SYSTEM
  SHALL return a non-zero number of log lines corresponding to that activity, once the
  root cause is fixed.
- WHEN the investigation is performed THE SYSTEM SHALL produce a documented root
  cause classification: (a) application not emitting logs at the queried level, (b)
  log shipper/agent misconfigured or not running, (c) Loki storage/retention issue,
  or (d) `mctl_get_service_logs` query scope/filter mismatch.
- IF the root cause is application-side (e.g., log level too restrictive, wrong
  stdout/stderr stream) THEN THE SYSTEM SHALL be reconfigured to emit logs at an
  appropriate level without requiring a Backstage version change.
- IF the root cause is shipper/pipeline-side (Loki, Promtail/agent, or equivalent)
  THEN THE SYSTEM SHALL have the shipping configuration corrected and validated with
  a test query before this proposal is considered complete.
- WHILE the investigation is in progress THE SYSTEM SHALL NOT have any production
  logging behavior changed without validating in a lower environment first, to avoid
  masking or losing existing (even if unreachable) log data.

## Out of scope
- Rebuilding or replacing the observability plugin itself (explicitly protected per
  `architecture.md`: "Do not propose removing the observability custom plugin").
- Introducing a new logging backend or vendor (e.g., migrating off Loki).
- Fixing unrelated metrics gaps (e.g., the ArgoCD `service` field null issue — tracked
  separately in `argocd-service-field-gap`).
