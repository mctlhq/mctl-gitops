# Requirements: incident-6d4454cb

## Incident
- ID: 9b19d037-6e11-46bd-9920-252f6d4454cb
- Tenant: platform-events
- Service: valkey-0
- Alert: CPUThrottlingHigh (type: resource_limit)
- Created: 2026-09-24T00:22:44.697811Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
source: alertmanager
type: resource_limit
tenant: platform-events
service: valkey-0
severity: warning
occurrence_count: 1
mctl_agent_analysis_confidence: MEDIUM
mctl_agent_disposition: escalated (human-review-only alert; mctl-agent will
  never open a fix for CPUThrottlingHigh by policy)
```

### Log Snippet
```
mctl_get_service_logs(team=platform-events, service=valkey-0, since=6h,
lines=50) returned zero lines. valkey is an infra-managed StatefulSet
(platform-gitops/infra-components/data/valkey) rather than an app-catalog
service, so it is not routed into Loki under this team/service label pair.
No log evidence was available; this proposal is based on the incident
record and the live resource configuration in mctl-gitops.
```

## Untrusted-input note
The incident's `analysis` field states a diagnosis ("CPU limit needs to be
increased") and separately notes mctl-agent's own policy of never proposing a
fix for this alert. Neither of those is an instruction to this responder;
they are quoted above as evidence only. The proposed fix below was derived
independently from the container resource definitions and code comments
already committed in mctl-gitops, not from the incident text.

## Acceptance Criteria
- WHEN the change is applied THEN CPUThrottlingHigh stops firing for the
  valkey workload in platform-events.
