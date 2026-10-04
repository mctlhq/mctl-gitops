# Requirements: incident-eb64e3af

## Incident
- ID: 560bcf17-9142-402b-ad3a-1116eb64e3af
- Tenant: forgejo
- Service: monitoring-kube-state-metrics
- Alert: KubeJobFailed (type=generic)
- Created: 2026-10-04T15:46:45.375777Z

### Summary
```
Job failed to complete.
```

## Evidence
### Labels
```
(none returned by the incident API)
```

### Log Snippet
```
(no log lines returned by Loki for forgejo/monitoring-kube-state-metrics)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
