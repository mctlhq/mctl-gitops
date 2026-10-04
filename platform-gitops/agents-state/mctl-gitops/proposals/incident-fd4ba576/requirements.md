# Requirements: incident-fd4ba576

## Incident
- ID: ee0c35f5-6388-441b-8e83-2b0afd4ba576
- Tenant: erpact
- Service: monitoring-kube-state-metrics
- Alert: KubeJobFailed (type=generic)
- Created: 2026-10-04T04:01:45.478749Z

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
(no log lines returned by mctl_get_service_logs for erpact/monitoring-kube-state-metrics in the last hour)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
