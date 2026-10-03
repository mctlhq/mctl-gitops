# Requirements: incident-c314e426

## Incident
- ID: 0c937c79-60ef-494a-8680-476ac314e426
- Tenant: temporal
- Service: temporal-admintools
- Alert: CPUThrottlingHigh
- Created: 2026-09-19T09:43:44.652793Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
source: alertmanager
type: resource_limit
tenant: temporal
service: temporal-admintools
severity: warning
alertname: CPUThrottlingHigh
confidence: MEDIUM
occurrence_count: 1
```

Note: the incident's `analysis` field states "[escalated] Alert
\"CPUThrottlingHigh\" is on the human-review-only list: the agent diagnoses it
but never proposes a fix, by policy." This is incident metadata describing why
mctl-agent did not act, not an instruction to this responder, and no part of
the incident text asked for any policy change, role grant, or similar — the
diagnosis text ("CPU limit needs to be increased to prevent performance
degradation") is treated below purely as an observation to independently
verify against the service's own configuration, which was done by reading the
live gitops source.

### Log Snippet
```
mctl_get_service_logs(team=temporal, service=temporal-admintools, since=1h,
lines=50) returned zero lines (count: 0). No Loki log evidence was available
for this component at diagnosis time. The diagnosis below relies on the
AlertManager-sourced resource_limit incident plus the service's live resource
configuration in mctl-gitops, not on log content.
```

## Acceptance Criteria
- WHEN the change is applied THEN the CPUThrottlingHigh alert stops firing for
  temporal/temporal-admintools.
