# Requirements: incident-ebbb5e28

## Incident
- ID: f5171fe7-f98a-40fc-b406-b6daebbb5e28
- Tenant: erpact
- Service: monitoring-kube-state-metrics
- Alert: KubeJobFailed (type=generic)
- Created: 2026-10-20T11:53:45Z

### Summary
```
Job failed to complete.
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: erpact
service: monitoring-kube-state-metrics
```

### Log Snippet
```
(no log lines returned for erpact/monitoring-kube-state-metrics; the service
 is kube-state-metrics, which only reports the failed Job and is not the Job itself)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
