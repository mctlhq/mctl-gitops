# Requirements: incident-8646a75d

## Incident
- ID: c4731ebf-8b81-4969-b7e6-147b8646a75d
- Tenant: zitadel
- Service: monitoring-kube-state-metrics
- Alert: KubeJobFailed (type=generic)
- Created: 2026-11-21T10:34:45.498466Z

### Summary
```
Job failed to complete.
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
type: generic
```

### Log Snippet
```
No logs available: mctl_get_service_logs, mctl_list_namespace_events returned "tenant not found: zitadel".
```

## Acceptance Criteria
- WHEN the change is applied THEN the KubeJobFailed alert stops firing for the zitadel namespace.
