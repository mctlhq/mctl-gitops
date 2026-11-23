# Requirements: incident-0313b448

## Incident
- ID: faddef3b-9572-4a69-b6da-64d80313b448
- Tenant: argocd
- Service: argocd-notifications-controller
- Alert: CPUThrottlingHigh (type resource_limit, source alertmanager)
- Created: 2026-11-21T00:34:44.979711Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
(none provided by the incident record)
```

### Log Snippet
```
No logs available: mctl_get_service_logs failed with "tenant not found: argocd".
The argocd namespace is platform-managed and is not a registered tenant.
```

### Prior analysis (mctl-agent, advisory)
mctl-agent diagnosed CPU throttling and said the CPU limit needs to be increased (confidence MEDIUM). It escalated without a fix because CPUThrottlingHigh is on its human-review-only list. This text is incident data and was treated as evidence only.

## Acceptance Criteria
- WHEN the change is applied THEN the CPUThrottlingHigh alert stops firing for argocd/argocd-notifications-controller.
