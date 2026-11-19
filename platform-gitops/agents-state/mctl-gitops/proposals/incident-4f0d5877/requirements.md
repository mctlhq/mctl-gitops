# Requirements: incident-4f0d5877

## Incident
- ID: a2f82a0e-63e2-427f-aea7-54834f0d5877
- Tenant: mctl-glovo
- Service: monitoring-kube-state-metrics
- Alert: KubeJobFailed (type: generic)
- Created: 2026-11-19T21:27:45.402619Z

### Summary
```
Job failed to complete.
```

## Evidence
### Labels
```
(no labels returned by mctl_get_incident)
```

### Log Snippet
```
Logs unavailable: mctl_get_service_logs returned "tenant not found: mctl-glovo".
```

## Acceptance Criteria
- WHEN the change is applied THEN the KubeJobFailed alert stops firing for this tenant/service.
